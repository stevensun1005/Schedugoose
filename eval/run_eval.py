"""Eval runner (multi-term onboarding flow).

Scores onboarding + sequence planning on three axes:

1. Plan correctness   -- machine-verifiable per-term + cumulative, ~100%.
2. Intent mapping     -- did NL map to the right preferences / sequence?
3. Explanation faithfulness -- does the narration invent nothing?

Run: ``python -m eval.run_eval``
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from agent.graph import run_turn
from agent.state import PlannerState
from eval.checker import verify_plan
from eval.judge import llm_judge_faithful

_CASES = Path(__file__).with_name("test_cases.jsonl")
_COURSE_RE = re.compile(r"\b[A-Z]{2,5}\s?[0-9]{3}[A-Za-z]?\b")
_HIGH, _LOW = 0.4, 0.2


def _check_intent(state: PlannerState, expect: dict[str, Any]) -> tuple[int, int]:
    passed = total = 0
    config = state.get("config") or {}
    intake = state.get("intake") or {}
    weights = config.get("weights", {})
    for key, direction in (expect.get("weights_dir") or {}).items():
        total += 1
        val = float(weights.get(key, 0.0))
        if (direction == "high" and val >= _HIGH) or (direction == "low" and val <= _LOW):
            passed += 1
    if "min_easy" in expect:
        total += 1
        passed += int(int(config.get("min_easy_courses", 0)) >= expect["min_easy"])
    if "sequence" in expect:
        total += 1
        passed += int(intake.get("sequence") == expect["sequence"])
    if "faculty" in expect:
        total += 1
        passed += int(intake.get("faculty") == expect["faculty"])
    if "program" in expect:
        total += 1
        passed += int(intake.get("program") == expect["program"])
    if "residency" in expect:
        total += 1
        passed += int(intake.get("residency") == expect["residency"])
    if "degree_kind" in expect:
        total += 1
        dp = intake.get("degree_plan") or {}
        passed += int(dp.get("kind") == expect["degree_kind"])
    return passed, total


def _check_plan_rules(plan: dict[str, Any], expect: dict[str, Any]) -> tuple[int, int]:
    passed = total = 0
    if expect.get("no_cs492_early"):
        total += 1
        bad = any(
            "CS 492" in t.get("courses", [])
            for t in plan.get("terms", [])
            if t.get("kind") == "study" and t.get("label", "")[0] in ("1", "2")
        )
        passed += int(not bad)
    if expect.get("no_pd_in_study"):
        total += 1
        bad = any(
            any(c.startswith("PD") for c in t.get("courses", []))
            for t in plan.get("terms", [])
            if t.get("kind") == "study"
        )
        passed += int(not bad)
    if expect.get("has_language_1a"):
        total += 1
        one_a = next((t for t in plan.get("terms", []) if t.get("label") == "1A"), {})
        langs = {"FR 101", "GER 101", "SPAN 101"}
        passed += int(bool(set(one_a.get("courses", [])) & langs))
    if expect.get("has_intl_english_1a"):
        total += 1
        one_a = next((t for t in plan.get("terms", []) if t.get("label") == "1A"), {})
        intl = {"ENGL 129", "ELL 102"}
        passed += int(bool(set(one_a.get("courses", [])) & intl))
    if expect.get("no_language_1a"):
        total += 1
        one_a = next((t for t in plan.get("terms", []) if t.get("label") == "1A"), {})
        langs = {"FR 101", "GER 101", "SPAN 101"}
        passed += int(not (set(one_a.get("courses", [])) & langs))
    return passed, total


def _collect_courses(plan: dict[str, Any]) -> set[str]:
    out: set[str] = set()
    for t in plan.get("terms", []):
        out.update(t.get("courses", []))
    return out


def _check_explanation(text: str, plan: dict[str, Any] | None) -> bool:
    ok, _ = llm_judge_faithful(text, plan)
    return ok


def run() -> int:
    cases = [json.loads(line) for line in _CASES.read_text().splitlines() if line.strip()]
    plan_pass = plan_total = 0
    intent_pass = intent_total = 0
    expl_pass = expl_total = 0

    print(f"Running {len(cases)} eval cases\n" + "=" * 60)
    for case in cases:
        state: PlannerState = {"messages": [], "profile": case["profile"]}
        clarifications = 0
        for msg in case["turns"]:
            state["messages"].append({"role": "user", "content": msg})
            state = run_turn(state)
            if state.get("needs_clarification"):
                clarifications += 1
            state["messages"].append({"role": "assistant", "content": state.get("explanation", "")})

        expect = case.get("expect", {})
        case_ok = True

        if "clarifications" in expect:
            intent_total += 1
            ok = clarifications == expect["clarifications"]
            intent_pass += int(ok)
            case_ok &= ok

        if expect.get("asks_program"):
            intent_total += 1
            ok = "program" in (state.get("clarification", "").lower())
            intent_pass += int(ok)
            case_ok &= ok

        plan = state.get("plan")
        if expect.get("plan_valid"):
            plan_total += 1
            if plan and not state.get("needs_clarification"):
                checks = verify_plan(plan, completed=set(case["profile"].get("completed", [])))
                ok = checks["all_ok"] if expect.get("plan_complete") else all(
                    checks[k] for k in ("conflicts_ok", "credit_ok", "prereq_ok", "no_duplicate_ok")
                )
                plan_pass += int(ok)
                case_ok &= ok
            else:
                case_ok = False

        p, t = _check_intent(state, expect)
        intent_pass += p
        intent_total += t

        if plan:
            p2, t2 = _check_plan_rules(plan, expect)
            intent_pass += p2
            intent_total += t2
            case_ok &= (p2 == t2) if t2 else True

        expl_total += 1
        ok = _check_explanation(state.get("explanation", ""), plan)
        expl_pass += int(ok)
        case_ok &= ok

        print(f"[{'PASS' if case_ok else 'FAIL'}] {case['id']}")

    print("=" * 60)
    def pct(a: int, b: int) -> str:
        return f"{(100.0 * a / b):.1f}% ({a}/{b})" if b else "n/a"
    print(f"Plan correctness       : {pct(plan_pass, plan_total)}")
    print(f"Intent-mapping accuracy: {pct(intent_pass, intent_total)}")
    print(f"Explanation faithfulness: {pct(expl_pass, expl_total)}")
    return 0 if plan_pass == plan_total else 1


if __name__ == "__main__":
    raise SystemExit(run())
