"""Step-by-step E2E replay of the user's manual test conversation."""

from __future__ import annotations

import json
import sys
import textwrap
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000"

STEPS: list[tuple[str, dict[str, object]]] = [
    ("hi", {"expect_llm_explained": True, "no_template": True, "no_full_plan": True}),
    ("im enrolled in cs", {"expect_llm_explained": True, "no_template": True, "no_full_plan": True}),
    ("international", {"expect_llm_explained": True, "no_template": True, "no_full_plan": True}),
    ("coop", {"expect_llm_explained": True, "no_template": True, "no_full_plan": True}),
    ("fall 2026", {"expect_plan": True, "allow_template": True}),
    (
        "i dont want to take music",
        {"expect_plan": True, "music_not_in_1a": True, "no_template_preferred": True},
    ),
    (
        "i want to be data science in the future, is there any courses you recommend relating to the field",
        {
            "expect_plan": True,
            "advisory": True,
            "no_template": True,
            "mentions_ds_courses": True,
            "no_stale_music_note": True,
        },
    ),
    (
        "i want you to explain to me",
        {"expect_plan": True, "advisory": True, "no_template": True},
    ),
    (
        "i want to be ds in the future, any course you recommend?",
        {"advisory": True, "no_template": True, "mentions_ds_courses": True},
    ),
    (
        "i want you to explain",
        {"advisory": True, "no_template": True},
    ),
    (
        "you are not explaining. dont use template",
        {"advisory": True, "no_template": True, "expect_llm_explained": True},
    ),
]

TEMPLATE_MARKERS = (
    "Agent pipeline (",
    "Tell me to make a term lighter, avoid mornings, swap a course",
    "Here's a term-by-term plan for",
)

DS_COURSE_HINTS = ("STAT", "CS 486", "CS 480", "data science", "machine learning", "ML")


def post_plan(message: str, session_id: str | None) -> dict:
    body = {"message": message, "profile": {"completed": []}}
    if session_id:
        body["session_id"] = session_id
    req = urllib.request.Request(
        f"{BASE}/plan",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read())


def health() -> dict:
    with urllib.request.urlopen(f"{BASE}/health", timeout=10) as resp:
        return json.loads(resp.read())


def is_template(text: str) -> bool:
    return any(m in text for m in TEMPLATE_MARKERS)


def courses_in_term(plan: dict | None, label: str) -> list[str]:
    if not plan:
        return []
    for t in plan.get("terms", []):
        if t.get("label") == label:
            return list(t.get("courses") or [])
    return []


def check(step: int, msg: str, data: dict, rules: dict[str, object]) -> list[str]:
    fails: list[str] = []
    expl = data.get("explanation") or ""
    plan = data.get("plan")

    if rules.get("expect_plan") and not plan:
        fails.append("expected plan but got none")

    if rules.get("no_full_plan") and plan:
        fails.append("expected no plan yet but plan was returned")

    if rules.get("expect_llm_explained") and not data.get("llm_explained"):
        fails.append(f"expected llm_explained=True, got {data.get('llm_explained')}")

    if rules.get("no_template") and is_template(expl):
        fails.append("response looks like template dump")

    if rules.get("no_template_preferred") and is_template(expl) and not data.get("llm_explained"):
        fails.append("template fallback when AI explain was preferred")

    if rules.get("advisory") and is_template(expl):
        fails.append("advisory turn still used template")

    if rules.get("mentions_ds_courses") and not any(h in expl for h in DS_COURSE_HINTS):
        fails.append(f"no DS course hints in: {expl[:200]}...")

    if rules.get("no_stale_music_note") and "Excluded **MUSIC" in expl:
        fails.append("stale MUSIC pin note on advisory turn")

    if rules.get("music_not_in_1a"):
        one_a = courses_in_term(plan, "1A")
        if any("MUSIC" in c for c in one_a):
            fails.append(f"MUSIC still in 1A: {one_a}")

    if rules.get("allow_template"):
        pass  # first plan may be template OK

    badge = []
    if data.get("llm_understood"):
        badge.append("understood")
    if data.get("llm_explained"):
        badge.append("explained")
    if data.get("llm_parse_failed"):
        badge.append("parse_failed")

    print(f"\n{'='*72}")
    print(f"STEP {step}: {msg!r}")
    print(f"  badge: {', '.join(badge) or 'rules-only'} | plan: {'yes' if plan else 'no'}")
    print(f"  reply: {textwrap.shorten(expl.replace(chr(10), ' '), width=220)}")
    if plan and rules.get("music_not_in_1a"):
        print(f"  1A: {courses_in_term(plan, '1A')}")

    return fails


def main() -> int:
    try:
        h = health()
    except urllib.error.URLError as exc:
        print(f"FAIL: server not reachable at {BASE} — {exc}")
        return 1

    print(f"Health: llm={h.get('llm')} mode={h.get('llm_mode')} uw={h.get('uw_data_source')}")
    if not h.get("llm"):
        print("WARN: GROQ_API_KEY not loaded — some steps will differ from live Groq test")

    session_id: str | None = None
    all_fails: list[str] = []

    for i, (msg, rules) in enumerate(STEPS, 1):
        try:
            data = post_plan(msg, session_id)
        except Exception as exc:
            print(f"\nSTEP {i} FAIL: request error — {exc}")
            all_fails.append(f"step {i}: request error")
            break
        session_id = data.get("session_id") or session_id
        fails = check(i, msg, data, rules)
        for f in fails:
            all_fails.append(f"step {i}: {f}")

    print(f"\n{'='*72}")
    if all_fails:
        print(f"FAILED ({len(all_fails)} issues):")
        for f in all_fails:
            print(f"  - {f}")
        return 1
    print("ALL STEPS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
