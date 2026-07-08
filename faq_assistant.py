#!/usr/bin/env python3
"""FAQ assistant and evaluator for fund 009049."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE_PATH = ROOT / "data" / "fund_009049_knowledge.json"
EVAL_PATH = ROOT / "data" / "eval_questions.jsonl"
REPORT_PATH = ROOT / "reports" / "eval_report.json"


@dataclass
class Answer:
    text: str
    fact_id: str
    category: str
    source_names: list[str]
    source_urls: list[str]
    date: str
    refused: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "fact_id": self.fact_id,
            "category": self.category,
            "source_names": self.source_names,
            "source_urls": self.source_urls,
            "date": self.date,
            "refused": self.refused,
        }


def load_knowledge(path: Path = KNOWLEDGE_PATH) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def normalize(text: str) -> str:
    return re.sub(r"\s+", "", text.lower())


def score_fact(question: str, fact: dict[str, Any]) -> int:
    question_norm = normalize(question)
    score = 0
    for pattern in fact.get("question_patterns", []):
        pattern_norm = normalize(pattern)
        if pattern_norm and pattern_norm in question_norm:
            score += 8
    for keyword in fact.get("keywords", []):
        keyword_norm = normalize(keyword)
        if keyword_norm and keyword_norm in question_norm:
            score += 3
    return score


def select_fact(question: str, facts: list[dict[str, Any]]) -> dict[str, Any]:
    compliance_fact = next(fact for fact in facts if fact["id"] == "compliance_refusal")
    if score_fact(question, compliance_fact) > 0:
        return compliance_fact

    scored = sorted(
        ((score_fact(question, fact), fact) for fact in facts),
        key=lambda item: item[0],
        reverse=True,
    )
    if scored and scored[0][0] > 0:
        return scored[0][1]
    return next(fact for fact in facts if fact["id"] == "profile_basic")


def build_answer(question: str, knowledge: dict[str, Any]) -> Answer:
    fact = select_fact(question, knowledge["facts"])
    sources = {source["id"]: source for source in knowledge["sources"]}
    selected_sources = [sources[source_id] for source_id in fact.get("source_ids", [])]
    source_names = [source["name"] for source in selected_sources]
    source_urls = [source["url"] for source in selected_sources]
    refused = fact["id"] == "compliance_refusal"

    lines = [fact["answer"]]
    if not refused:
        lines.append(f"数据/资料时点：{fact['date']}。")
    lines.append("来源：" + "；".join(f"{source['name']}（{source['url']}）" for source in selected_sources) + "。")
    lines.append(knowledge["standard_disclaimer"])

    return Answer(
        text="\n".join(lines),
        fact_id=fact["id"],
        category=fact["category"],
        source_names=source_names,
        source_urls=source_urls,
        date=fact["date"],
        refused=refused,
    )


def load_eval_cases(path: Path = EVAL_PATH) -> list[dict[str, Any]]:
    cases = []
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    return cases


def evaluate_case(case: dict[str, Any], answer: Answer) -> dict[str, Any]:
    answer_norm = normalize(answer.text)
    expected_hits = [
        expected
        for expected in case["expected_contains"]
        if normalize(expected) in answer_norm
    ]
    expected_ok = len(expected_hits) == len(case["expected_contains"])
    refusal_ok = (not case["requires_refusal"]) or answer.refused
    source_ok = "来源：" in answer.text and bool(answer.source_urls)
    date_ok = (not case["requires_date"]) or "数据/资料时点" in answer.text or "数据日期" in answer.text
    passed = expected_ok and refusal_ok and source_ok and date_ok
    return {
        "id": case["id"],
        "question": case["question"],
        "answer": answer.text,
        "fact_id": answer.fact_id,
        "category": answer.category,
        "expected_hits": expected_hits,
        "missing_expected": [
            expected for expected in case["expected_contains"] if expected not in expected_hits
        ],
        "expected_ok": expected_ok,
        "refusal_ok": refusal_ok,
        "source_ok": source_ok,
        "date_ok": date_ok,
        "passed": passed,
    }


def run_eval() -> dict[str, Any]:
    knowledge = load_knowledge()
    cases = load_eval_cases()
    results = [evaluate_case(case, build_answer(case["question"], knowledge)) for case in cases]
    passed_count = sum(1 for result in results if result["passed"])
    refusal_cases = [case for case in cases if case["requires_refusal"]]
    refusal_passed = sum(
        1
        for case, result in zip(cases, results)
        if case["requires_refusal"] and result["refusal_ok"]
    )
    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "fund_code": knowledge["fund_code"],
        "fund_name": knowledge["fund_name"],
        "summary": {
            "total": len(results),
            "passed": passed_count,
            "accuracy": round(passed_count / len(results), 4) if results else 0,
            "refusal_total": len(refusal_cases),
            "refusal_passed": refusal_passed,
            "refusal_accuracy": round(refusal_passed / len(refusal_cases), 4) if refusal_cases else 0,
        },
        "results": results,
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with REPORT_PATH.open("w", encoding="utf-8") as file:
        json.dump(report, file, ensure_ascii=False, indent=2)
    return report


def print_answer(question: str) -> None:
    answer = build_answer(question, load_knowledge())
    print(answer.text)


def answer_question(question: str) -> dict[str, Any]:
    return build_answer(question, load_knowledge()).to_dict()


def print_eval() -> None:
    report = run_eval()
    summary = report["summary"]
    print(f"基金：{report['fund_name']}（{report['fund_code']}）")
    print(f"测试题数：{summary['total']}")
    print(f"通过：{summary['passed']}")
    print(f"准确率：{summary['accuracy']:.2%}")
    print(f"拒答准确率：{summary['refusal_accuracy']:.2%}")
    print(f"报告：{REPORT_PATH}")


def main() -> None:
    parser = argparse.ArgumentParser(description="009049 FAQ assistant prototype")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ask_parser = subparsers.add_parser("ask", help="ask one question")
    ask_parser.add_argument("question")
    subparsers.add_parser("eval", help="run batch evaluation")

    args = parser.parse_args()
    if args.command == "ask":
        print_answer(args.question)
    elif args.command == "eval":
        print_eval()


if __name__ == "__main__":
    main()
