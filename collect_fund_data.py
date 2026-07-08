#!/usr/bin/env python3
"""Collect public fund data for 009049 and update the local knowledge base."""

from __future__ import annotations

import argparse
from html.parser import HTMLParser
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
FEE_URL = f"https://fundf10.eastmoney.com/jjfl_{FUND_CODE}.html"


class CollectionError(RuntimeError):
    pass


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        text = " ".join(data.replace("\xa0", " ").split())
        if text:
            self.parts.append(text)


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
        match = re.search(rf"(?:var\s+)?{name}\s*=", text)
        if not match:
            return None
        index = match.end()
        while index < len(text) and text[index].isspace():
            index += 1
        if index >= len(text) or text[index] not in "[{":
            return None
        opener = text[index]
        closer = "]" if opener == "[" else "}"
        depth = 0
        in_string = False
        escape = False
        end = index
        while end < len(text):
            char = text[end]
            if in_string:
                if escape:
                    escape = False
                elif char == "\\":
                    escape = True
                elif char == '"':
                    in_string = False
            else:
                if char == '"':
                    in_string = True
                elif char == opener:
                    depth += 1
                elif char == closer:
                    depth -= 1
                    if depth == 0:
                        end += 1
                        break
            end += 1
        raw = text[index:end].strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    net_worth_trend = extract_json("Data_netWorthTrend") or []
    ac_worth_trend = extract_json("Data_ACWorthTrend") or []
    latest_net_worth = net_worth_trend[-1] if net_worth_trend else {}
    latest_ac_worth = ac_worth_trend[-1] if ac_worth_trend else []
    managers = extract_json("Data_currentFundManager") or []

    return {
        "fund_name": extract_string("fS_name"),
        "fund_code": extract_string("fS_code"),
        "net_worth_latest": latest_net_worth,
        "accumulated_worth_latest": latest_ac_worth,
        "net_worth_count": len(net_worth_trend),
        "managers": managers,
    }


def html_text_parts(text: str) -> list[str]:
    parser = TextExtractor()
    parser.feed(text)
    return parser.parts


def token_after(parts: list[str], label: str) -> str | None:
    try:
        index = parts.index(label)
    except ValueError:
        return None
    if index + 1 >= len(parts):
        return None
    return parts[index + 1]


def parse_purchase_rows(parts: list[str]) -> list[dict[str, str]]:
    try:
        start = parts.index("申购费率")
    except ValueError:
        return []
    rows = []
    index = start + 5
    while index + 1 < len(parts):
        amount = parts[index]
        if amount == "友情提示：" or amount == "赎回费率":
            break
        original = parts[index + 1]
        discount = ""
        if index + 2 < len(parts) and parts[index + 2].startswith("|"):
            discount = parts[index + 2].replace("|", "").strip()
            index += 3
        else:
            index += 2
        rows.append(
            {
                "amount": amount,
                "original_rate": original,
                "eastmoney_discount_rate": discount,
            }
        )
    return rows


def parse_redeem_rows(parts: list[str]) -> list[dict[str, str]]:
    try:
        start = parts.index("赎回费率")
    except ValueError:
        return []
    rows = []
    index = start + 3
    while index + 1 < len(parts):
        holding_period = parts[index]
        if holding_period in {"友情提示：", "注："}:
            break
        rows.append({"holding_period": holding_period, "rate": parts[index + 1]})
        index += 2
    return rows


def parse_fee_page(text: str) -> dict[str, Any]:
    parts = html_text_parts(text)
    return {
        "management_fee": token_after(parts, "管理费率"),
        "custodian_fee": token_after(parts, "托管费率"),
        "sales_service_fee": token_after(parts, "销售服务费率"),
        "purchase_fee_rows": parse_purchase_rows(parts),
        "redeem_fee_rows": parse_redeem_rows(parts),
    }


def collect() -> dict[str, Any]:
    timestamp = int(time.time() * 1000)
    realtime_text = fetch_text(f"{REALTIME_URL}?rt={timestamp}")
    profile_text = fetch_text(PROFILE_SCRIPT_URL)
    fee_text = fetch_text(FEE_URL)
    realtime = parse_jsonp(realtime_text)
    profile = parse_profile_script(profile_text)
    fees = parse_fee_page(fee_text)
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
            {
                "id": "eastmoney_fee",
                "name": "天天基金基金费率页",
                "url": FEE_URL,
            },
        ],
        "realtime": realtime,
        "profile": profile,
        "fees": fees,
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
    fees = collected.get("fees", {})
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

    managers = profile.get("managers") or []
    manager_names = [manager.get("name") for manager in managers if manager.get("name")]
    manager_date = (
        managers[0].get("power", {}).get("jzrq")
        if managers and isinstance(managers[0].get("power"), dict)
        else collected["collected_at"][:10]
    )
    if manager_names:
        manager_answer = (
            f"{fund_name}（{FUND_CODE}）的基金经理为{'、'.join(manager_names)}。"
            f"基金经理信息采集自东方财富基金数据脚本，数据日期为 {manager_date}。"
            "基金经理可能随基金公司公告调整，请以易方达基金官网、基金产品资料概要或最新公告披露为准。"
        )
        update_fact(
            knowledge,
            "manager",
            manager_answer,
            manager_date,
            ["eastmoney_profile_script", "efunds_official"],
        )

    if fees.get("purchase_fee_rows") or fees.get("redeem_fee_rows"):
        purchase_summary = "；".join(
            f"{row['amount']}：原费率{row['original_rate']}"
            + (f"，天天基金优惠费率{row['eastmoney_discount_rate']}" if row.get("eastmoney_discount_rate") else "")
            for row in fees.get("purchase_fee_rows", [])[:4]
        )
        redeem_summary = "；".join(
            f"{row['holding_period']}：{row['rate']}"
            for row in fees.get("redeem_fee_rows", [])[:5]
        )
        fee_answer = (
            f"{FUND_CODE} 为A类份额。根据天天基金基金费率页采集信息，"
            f"申购费率为：{purchase_summary or '未获取'}。"
            f"赎回费率按持有期限分档：{redeem_summary or '未获取'}。"
            f"运作费用方面，管理费率为{fees.get('management_fee') or '未获取'}，"
            f"托管费率为{fees.get('custodian_fee') or '未获取'}，"
            f"销售服务费率为{fees.get('sales_service_fee') or '未获取'}。"
            "费率可能因销售渠道、申购金额、持有期限和基金公司公告调整而变化，请以基金公司和销售机构最新披露为准。"
        )
        update_fact(
            knowledge,
            "fees",
            fee_answer,
            collected["collected_at"][:10],
            ["eastmoney_fee", "efunds_official"],
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
    fees = collected.get("fees", {})
    managers = profile.get("managers") or []
    print(f"基金代码：{FUND_CODE}")
    print(f"采集时间：{collected['collected_at']}")
    print(f"基金名称：{realtime.get('name') or profile.get('fund_name') or '未获取'}")
    print(f"基金经理：{'、'.join(manager.get('name', '') for manager in managers if manager.get('name')) or '未获取'}")
    print(f"净值日期：{realtime.get('jzrq') or '未获取'}")
    print(f"单位净值：{realtime.get('dwjz') or '未获取'}")
    print(f"实时估值：{realtime.get('gsz') or '未获取'}")
    print(f"估算涨跌幅：{realtime.get('gszzl') or '未获取'}")
    print(f"管理费率：{fees.get('management_fee') or '未获取'}")
    print(f"托管费率：{fees.get('custodian_fee') or '未获取'}")
    print(f"销售服务费率：{fees.get('sales_service_fee') or '未获取'}")
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
