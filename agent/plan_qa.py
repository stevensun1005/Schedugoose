"""Deterministic answers to common questions about an existing plan.

These are factual and read straight from the plan (graduation term, work terms,
counts), so they never need the LLM and never hallucinate. Also covers help,
greetings, and off-topic redirects so a plan turn isn't answered by re-dumping
the whole schedule.
"""

from __future__ import annotations

from typing import Any

from agent.state import PlannerState, last_user_message


def _low(state: PlannerState) -> str:
    return last_user_message(state).lower().strip().strip("!.。?？ ")


def is_reset(state: PlannerState) -> bool:
    low = _low(state)
    return low in (
        "start over", "reset", "restart", "start again", "clear", "new plan",
        "start fresh", "从头开始", "重新开始",
    ) or low.startswith(("start over", "start again", "restart from"))


def is_help_request(state: PlannerState) -> bool:
    low = _low(state)
    return any(p in low for p in (
        "what can you do", "what do you do", "how do you work", "how does this work",
        "what can i ask", "what can you help", "help me with", "your features",
        "how to use", "what are you", "who are you",
    )) or low in ("help", "/help", "?", "commands")


def help_text() -> str:
    return (
        "I'm Schedugoose — I plan your UW courses term by term across co-op. Once you "
        "have a plan you can ask me to:\n"
        "  • **Revise** it — \"make 2A lighter\", \"no music in 1A\", \"avoid mornings\", "
        "\"add CS 246 to 2B\", \"swap X for Y\"\n"
        "  • **Explain** choices — \"why CS 341 in 3A?\", \"explain my plan\"\n"
        "  • **Look up a course** — \"what is CS 246?\", \"prereqs for CS 486?\"\n"
        "  • **Career advice** — \"what courses for data science?\"\n"
        "  • **Requirements** — \"what do I need to graduate?\", \"standard first-year courses?\"\n"
        "  • **Plan facts** — \"show my plan\", \"when do I graduate?\", \"when are my work terms?\"\n"
        "  • **Change your profile** — \"change my start to Winter 2027\", \"switch to sequence 2\"\n"
        "Just tell me in plain language."
    )


def wants_course_search(state: PlannerState) -> bool:
    low = _low(state)
    return any(p in low for p in (
        "courses about", "courses on", "courses related to", "courses that cover",
        "which courses cover", "find courses", "classes about", "courses in",
        "courses for learning", "courses teaching",
    ))


def answer_course_search(state: PlannerState) -> str:
    from data.vector_store import search

    query = last_user_message(state)
    hits = search(query, top_k=5)
    if not hits:
        return "I couldn't find matching courses. Try naming a topic like 'databases' or 'machine learning'."
    lines = ["Courses that best match, by semantic search over the catalog:"]
    for cid, text, score in hits:
        title = text.split(" — ", 1)[-1].split(".")[0] if " — " in text else cid
        lines.append(f"  • **{cid}** — {title}")
    lines.append("Ask me to add one to a term, or 'what is <code>' for details.")
    return "\n".join(lines)


def is_smalltalk(state: PlannerState) -> bool:
    low = _low(state)
    return low in (
        "hi", "hello", "hey", "yo", "hi there", "hello there", "thanks", "thank you",
        "thx", "ty", "bye", "goodbye", "cool", "nice", "great", "ok", "okay", "👍",
        "你好", "谢谢", "再见",
    )


def smalltalk_reply(state: PlannerState) -> str:
    low = _low(state)
    if any(w in low for w in ("thank", "thx", "ty", "谢谢")):
        return "You're welcome! Ask me to tweak a term, explain a choice, or look up a course anytime."
    if any(w in low for w in ("bye", "goodbye", "再见")):
        return "See you! Your plan is saved for this session — come back to adjust it whenever."
    return "Hey! Your plan's ready above. Want to change a term, explain a choice, or check a course?"


def wants_plan_summary(state: PlannerState) -> bool:
    low = _low(state)
    return any(p in low for p in (
        "show my plan", "show me my plan", "show the plan", "my schedule", "my plan",
        "see my plan", "summarize my plan", "summarise my plan", "full plan",
        "whole plan", "what's my schedule", "whats my schedule", "recap",
    ))


def wants_graduation_q(state: PlannerState) -> bool:
    low = _low(state)
    return any(p in low for p in (
        "when do i graduate", "graduation", "when will i graduate", "on track",
        "finish my degree", "when do i finish", "when am i done", "how long until i graduate",
    ))


def answer_graduation(plan: dict[str, Any]) -> str:
    study = [t for t in plan.get("terms", []) if t.get("kind") == "study" and t.get("courses")]
    grad = study[-1] if study else None
    total = plan.get("total_courses", "?")
    target = plan.get("graduation_target_units", 20.0)
    units = plan.get("total_units", "?")
    if not grad:
        return "I don't have a completed plan to check graduation against yet."
    lines = [
        f"You graduate after **{grad['label']} ({grad['display']})** — your last study term.",
        f"That's **{total} courses / {units} of {target} academic credits**.",
    ]
    if plan.get("complete"):
        lines.append("You're **on track**: all core and category requirements are covered. ✅")
    else:
        rem = plan.get("remaining_requirements") or {}
        if rem:
            need = ", ".join(f"{k} (+{v})" for k, v in rem.items())
            lines.append(f"Still to cover: {need}. Ask me to fit these in and I'll re-plan.")
    return "\n".join(lines)


def wants_workterm_q(state: PlannerState) -> bool:
    low = _low(state)
    return any(p in low for p in (
        "work term", "work-term", "co-op term", "coop term", "when are my work",
        "how many co-op", "how many work", "when do i work", "my work terms", "wt",
    ))


def answer_workterms(plan: dict[str, Any]) -> str:
    works = [t for t in plan.get("terms", []) if t.get("kind") == "work"]
    if not works:
        return "Your sequence has no co-op work terms — it's a regular (non-co-op) plan."
    lines = [f"You have **{len(works)} co-op work terms** in this sequence:"]
    for t in works:
        pd = ", ".join(c for c in t.get("courses", []) if c.startswith("PD"))
        extra = f" (+ {pd})" if pd else ""
        lines.append(f"  • {t['label']} — {t['display']}{extra}")
    lines.append("Work terms carry no academic courses (just PD); they don't count toward the 20 credits.")
    return "\n".join(lines)


def wants_workload_q(state: PlannerState) -> bool:
    low = _low(state)
    return any(p in low for p in (
        "how heavy", "how hard", "how tough", "how difficult", "hardest term",
        "heaviest", "lightest term", "easiest term", "workload", "which term is hard",
        "which term is the hard", "how's 2a", "how is 2a",
    ))


def answer_workload(state: PlannerState, plan: dict[str, Any]) -> str:
    import re

    from data.uw_api import fetch_courses

    easi = {c.course_id: c.easiness for c in fetch_courses()}
    terms = [t for t in plan.get("terms", []) if t.get("kind") == "study" and t.get("courses")]
    if not terms:
        return "There are no study terms to assess yet."

    def load(t: dict[str, Any]) -> float:  # higher = lighter
        vals = [easi.get(c, 0.5) for c in t["courses"] if not c.startswith("PD")]
        return sum(vals) / len(vals) if vals else 0.5

    m = re.search(r"\b([1-4][ab])\b", _low(state))
    if m:
        lbl = m.group(1).upper()
        t = next((x for x in terms if x["label"] == lbl), None)
        if t:
            desc = "lighter than average" if load(t) >= 0.6 else "on the heavier side"
            return f"**{lbl} ({t['display']})**: {', '.join(t['courses'])}. That term looks **{desc}**."
    hardest = min(terms, key=load)
    lightest = max(terms, key=load)
    return (
        f"Your heaviest term looks like **{hardest['label']} ({hardest['display']})** and your "
        f"lightest **{lightest['label']} ({lightest['display']})**, from course workload signals "
        "(a rough estimate). Ask me to make any term lighter."
    )


def wants_conflict_q(state: PlannerState) -> bool:
    low = _low(state)
    return any(w in low for w in ("conflict", "clash", "overlap", "same time"))


def answer_conflict(state: PlannerState, plan: dict[str, Any]) -> str:
    from agent.semantic import extract_course_codes

    codes = extract_course_codes(last_user_message(state))
    term_of = {c: t for t in plan.get("terms", []) for c in t.get("courses", [])}
    if len(codes) >= 2:
        a, b = codes[0], codes[1]
        ta, tb = term_of.get(a), term_of.get(b)
        if ta and tb and ta["label"] == tb["label"]:
            return (
                f"{a} and {b} are both in **{ta['label']}** and it's conflict-free — "
                "I never place clashing section times in the same term."
            )
        if ta and tb:
            return f"No clash: {a} is in {ta['label']}, {b} in {tb['label']} — different terms."
    return (
        "Every term I build is conflict-free: the solver rejects any pair of overlapping "
        "sections, so nothing in your plan clashes."
    )


def wants_electives_q(state: PlannerState) -> bool:
    low = _low(state)
    return "elective" in low and any(p in low for p in (
        "what", "which", "list", "show", "can i take", "options", "available", "recommend", "suggest",
    ))


def answer_electives(plan: dict[str, Any]) -> str:
    from data.electives import easy_elective_options

    planned = {c for t in plan.get("terms", []) for c in t.get("courses", [])}
    opts = [o for o in easy_elective_options() if o["course_id"] not in planned][:6]
    if not opts:
        return "Your plan already uses the lighter electives I have. Ask me to swap one in for a course."
    lines = ["Some electives you could take (lighter / bird-course options not already in your plan):"]
    for o in opts:
        lines.append(f"  • {o['course_id']}: {o['title']}")
    lines.append('Tell me to add one, e.g. "add MUSIC 116 to 1A".')
    return "\n".join(lines)


_OFFTOPIC = (
    "weather", "joke", "who won", "sports", "stock", "recipe", "movie", "song",
    "president", "capital of", "translate", "love you", "your name mean",
)


def is_offtopic(state: PlannerState) -> bool:
    low = _low(state)
    from agent.semantic import extract_course_codes

    if extract_course_codes(low):
        return False
    return any(p in low for p in _OFFTOPIC)


def offtopic_reply() -> str:
    return (
        "That's outside what I do — I'm a UW course planner. I can build and adjust your "
        "term-by-term schedule, explain course choices, or answer course/requirement questions."
    )


def plan_qa_reply(state: PlannerState) -> str | None:
    """Deterministic reply for common plan questions, or None to fall through."""

    plan = state.get("plan") or {}
    if is_help_request(state):
        return help_text()
    if is_offtopic(state):
        return offtopic_reply()
    if wants_graduation_q(state):
        return answer_graduation(plan)
    if wants_workterm_q(state):
        return answer_workterms(plan)
    if wants_workload_q(state):
        return answer_workload(state, plan)
    if wants_conflict_q(state):
        return answer_conflict(state, plan)
    if wants_electives_q(state):
        return answer_electives(plan)
    if wants_plan_summary(state):
        return None  # handled by the caller (re-render the plan template)
    if is_smalltalk(state):
        return smalltalk_reply(state)
    return None
