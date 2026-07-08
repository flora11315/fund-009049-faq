#!/usr/bin/env python3
"""Collect public fund data for 009049 and update the local knowledge base."""

from __future__ import annotations

import argparse
import json
import re
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE_PATH = ROOT / "data" / "fund_009049_knowledge.json"
SNAPSHOT_PATH = ROOT / "data" / "fund_009049_collected.json"
FUND_CODE = "009049"

REALTIME_URL = f"https://fundgz.1234567.com.cn/js/{FUND_CODE}.js"
PROFILE_SCRIPT_URL = f"https://fund.eastmoney.com/pingzhongdata/{FUND_CODE}.js"


class CollectionError(RuntimeError):
    pass


def fetch_text(url: str, timeout: int = 12) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
            ),
            "Referer": "https://fund.eastmoney.com/",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            charset = charset.split(",")[0].strip()
            body = response.read()
            try:
                return body.decode(charset, errors="replace")
            except LookupError:
                for fallback in ("utf-8", "gbk"):
                    try:
                        return body.decode(fallback, errors="replace")
                    except LookupError:
                        continue
                return body.decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError) as exc:
        raise CollectionError(f"无法获取 {url}: {exc}") from exc


def parse_jsonp(text: str) -> dict[str, Any]:
    match = re.search(r"\((\{.*\})\)\s*;?\s*$", text, re.S)
    if not match:
        raise CollectionError("实时估值接口返回格式不是预期 JSONP。")
    return json.loads(match.group(1))


def parse_profile_script(text: str) -> dict[str, Any]:
    def extract_string(name: str) -> str | None:
        match = re.search(rf"var\s+{name}\s*=\s*['\"]([^'\"]*)['\"]", text)
        return match.group(1) if match else None

    def extract_json(name: str) -> Any:
        match = re.search(rf"var\s+{name}\s*=\s*(.*?);(?:\r?\n|$)", text, re.S)
        if not match:
            return None
        raw = match.group(1).strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    net_worth_trend = extract_json("Data_netWorthTrend") or []
    ac_worth_trend = extract_json("Data_ACWorthTrend") or []
    latest_net_worth = net_worth_trend[-1] if net_worth_trend else {}
    latest_ac_worth = ac_worth_trend[-1] if ac_worth_trend else []

    return {
        "fund_name": extract_string("fS_name"),
        "fund_code": extract_string("fS_code"),
        "net_worth_latest": latest_net_worth,
        "accumulated_worth_latest": latest_ac_worth,
        "net_worth_count": len(net_worth_trend),
    }


def collect() -> dict[str, Any]:
    timestamp = int(time.time() * 1000)
    realtime_text = fetch_text(f"{REALTIME_URL}?rt={timestamp}")
    profile_text = fetch_text(PROFILE_SCRIPT_URL)
    realtime = parse_jsonp(realtime_text)
    profile = parse_profile_script(profile_text)
    collected = {
        "fund_code": FUND_CODE,
        "collected_at": datetime.now().isoformat(timespec="seconds"),
        "sources": [
            {
                "id": "eastmoney_realtime",
                "name": "天天基金实时估值接口",
                "url": REALTIME_URL,
            },
            {
                "id": "eastmoney_profile_script",
                "name": "东方财富基金数据脚本",
                "url": PROFILE_SCRIPT_URL,
            },
        ],
        "realtime": realtime,
        "profile": profile,
    }
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with SNAPSHOT_PATH.open("w", encoding="utf-8") as file:
        json.dump(collected, file, ensure_ascii=False, indent=2)
    return collected


def upsert_source(knowledge: dict[str, Any], source: dict[str, str]) -> None:
    sources = knowledge.setdefault("sources", [])
    for existing in sources:
        if existing.get("id") == source["id"]:
            existing.update(source)
            return
    sources.append(source)


def update_fact(knowledge: dict[str, Any], fact_id: str, answer: str, date: str, source_ids: list[str]) -> None:
    for fact in knowledge["facts"]:
        if fact["id"] == fact_id:
            fact["answer"] = answer
            fact["date"] = date
            fact["source_ids"] = source_ids
            return
    raise CollectionError(f"知识库中找不到 fact: {fact_id}")


def merge_into_knowledge(collected: dict[str, Any]) -> dict[str, Any]:
    with KNOWLEDGE_PATH.open("r", encoding="utf-8") as file:
        knowledge = json.load(file)

    for source in collected["sources"]:
        upsert_source(knowledge, source)

    realtime = collected.get("realtime", {})
    profile = collected.get("profile", {})
    fund_name = realtime.get("name") or profile.get("fund_name") or knowledge["fund_name"]
    nav_date = realtime.get("jzrq") or collected["collected_at"][:10]
    unit_nav = realtime.get("dwjz")
    estimate = realtime.get("gsz")
    estimate_change = realtime.get("gszzl")
    estimate_time = realtime.get("gztime")

    if unit_nav:
        nav_answer = (
            f"{fund_name}（{FUND_CODE}）最近披露单位净值为 {unit_nav}，数据日期/净值日期为 {nav_date}。"
        )
        if estimate:
            nav_answer += f" 天天基金实时估值为 {estimate}，估算涨跌幅为 {estimate_change or '未披露'}%，估值时间为 {estimate_time or '未披露'}。"
        nav_answer += " 当前自动采集未接入同类排名字段；净值、估值和同类排名都属于高频变化数据，请以基金公司和销售机构最新披露为准。"
        update_fact(
            knowledge,
            "nav",
            nav_answer,
            nav_date,
            ["eastmoney_realtime", "eastmoney_profile", "efunds_official"],
        )

    if fund_name:
        profile_answer = (
            f"{FUND_CODE} 是{fund_name}，属于混合型基金和A类份额。"
            "基金管理人为易方达基金管理有限公司。"
        )
        update_fact(
            knowledge,
            "profile_basic",
            profile_answer,
            collected["collected_at"][:10],
            ["eastmoney_profile_script", "eastmoney_profile", "efunds_official"],
        )

    knowledge["as_of"] = collected["collected_at"][:10]
    knowledge["last_collection"] = {
        "collected_at": collected["collected_at"],
        "snapshot_path": str(SNAPSHOT_PATH),
        "status": "success",
    }
    with KNOWLEDGE_PATH.open("w", encoding="utf-8") as file:
        json.dump(knowledge, file, ensure_ascii=False, indent=2)
    return knowledge


def print_summary(collected: dict[str, Any], updated: bool) -> None:
    realtime = collected.get("realtime", {})
    profile = collected.get("profile", {})
    print(f"基金代码：{FUND_CODE}")
    print(f"采集时间：{collected['collected_at']}")
    print(f"基金名称：{realtime.get('name') or profile.get('fund_name') or '未获取'}")
    print(f"净值日期：{realtime.get('jzrq') or '未获取'}")
    print(f"单位净值：{realtime.get('dwjz') or '未获取'}")
    print(f"实时估值：{realtime.get('gsz') or '未获取'}")
    print(f"估算涨跌幅：{realtime.get('gszzl') or '未获取'}")
    print(f"快照文件：{SNAPSHOT_PATH}")
    print(f"知识库更新：{'是' if updated else '否'}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect public data for fund 009049")
    parser.add_argument("--no-update", action="store_true", help="only write snapshot, do not update knowledge base")
    args = parser.parse_args()
    collected = collect()
    if args.no_update:
        updated = False
    else:
        merge_into_knowledge(collected)
        updated = True
    print_summary(collected, updated)


if __name__ == "__main__":
    main()
