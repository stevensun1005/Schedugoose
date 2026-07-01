"""Degree-plan templates: major, minor, specialization, multi-major.

UW students differ on residency (language/English rules) and on how their
calendar is structured (Honours major only vs specialization vs minor vs
double/triple major). Requirements are merged additively from each component;
this is a simplified planning model, not a registrar transcript audit.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

Residency = Literal["international", "domestic"]
DegreeKind = Literal[
    "major",
    "major_specialization",
    "major_minor",
    "double_major",
    "triple_major",
]

# --- requirement building blocks (category -> min courses) ---------------- #
MAJORS: dict[str, dict[str, int]] = {
    "CS-Major": {
        "CS-Core": 8,
        "Math-Core": 6,
        "Comm": 1,
        "STAT-Core": 2,
        "CS-3xx": 3,
        "CS-4xx": 4,
        "Elective": 8,
    },
    "Math-Major": {
        "Math-Core": 10,
        "CS-Core": 2,
        "Comm": 1,
        "STAT-Core": 1,
        "Elective": 6,
    },
    # Mathematical Studies (BMath). Distilled from the UW calendar
    # (ucalendar: Mathematical Studies) — flexible plan, but it requires
    # MATH-faculty depth at the 300/400 level ("Math-3xx"), which the generic
    # Math-Major bucket doesn't capture.
    "MathStudies-Major": {
        "Math-Core": 7,
        "Math-3xx": 4,
        "CS-Core": 2,
        "Comm": 1,
        "Elective": 6,
    },
    "DataScience-Major": {
        "CS-Core": 5,
        "Math-Core": 3,
        "STAT-Core": 2,
        "STAT-ML": 1,
        "CS-AI": 1,
        "Comm": 1,
        "Elective": 6,
    },
    "Eng-Generic": {
        "CS-Core": 2,   # CS-major core (240+) is CS-students-only; 135/136 are open
        "Math-Core": 4,
        "Comm": 1,
        "Elective": 11,  # CS-3xx removed: those are CS-students-only too
    },
    "Science-Generic": {
        "CS-Core": 2,   # CS-major core (240+) is CS-students-only; 135/136 are open
        "Math-Core": 3,
        "Comm": 1,
        "STAT-Core": 1,
        "Elective": 10,
    },
}

# All eight UW CS specializations. Category minimums are the planner-facing view;
# full course requirements + sources live in data/degree_requirements.py.
SPECIALIZATIONS: dict[str, dict[str, int]] = {
    "CS-AI-Specialization": {"CS-AI": 2, "STAT-ML": 1, "CS-4xx": 1},
    "CS-Computational-Math-Specialization": {"Math-Core": 2, "CS-Theory": 1},
    "CS-HCI-Specialization": {"CS-3xx": 1, "Elective": 1},
    "CS-Business-Specialization": {"Elective": 2, "Comm": 1},
    "CS-Game-Design-Specialization": {"CS-4xx": 1, "Elective": 1},
    "CS-Digital-Hardware-Specialization": {"Elective": 2},
    # These need subjects outside the catalog (BIOL / FINE); selectable + citable
    # but planned only at the category level.
    "CS-Bioinformatics-Specialization": {},
    "CS-Computational-Fine-Art-Specialization": {},
}

MINORS: dict[str, dict[str, int]] = {
    "Stats-Minor": {"STAT-Core": 3, "Math-Minor": 1},
    "Math-Minor": {"Math-Core": 4, "Math-Minor": 2},
    "PMath-Minor": {"Math-Core": 4},
    "CO-Minor": {"Math-Core": 4},
    "Economics-Minor": {"Elective": 3},
    "Psych-Minor": {"Elective": 3},
}

# Language / English categories used by the planner (see mock_data tags).
DOMESTIC_LANGUAGE_CATEGORY = "Language"       # FREN / GER / SPAN second language
INTL_ENGLISH_CATEGORY = "Intl-English"        # ENGL 129 / ELL for intl students


@dataclass(frozen=True)
class DegreePlan:
    kind: DegreeKind
    primary: str                    # reqs key into MAJORS
    specializations: tuple[str, ...] = ()
    minors: tuple[str, ...] = ()
    extra_majors: tuple[str, ...] = ()  # second / third major for double/triple

    def display(self) -> str:
        parts = [self.primary.replace("-Major", "").replace("-Generic", "")]
        for s in self.specializations:
            parts.append(s.replace("CS-", "").replace("-Specialization", " spec"))
        for m in self.minors:
            parts.append(m.replace("-Minor", " minor"))
        for m in self.extra_majors:
            parts.append(m.replace("-Major", " major"))
        label = {
            "major": "Honours major",
            "major_specialization": "Major + specialization",
            "major_minor": "Major + minor",
            "double_major": "Double major",
            "triple_major": "Triple major",
        }[self.kind]
        return f"{label}: {', '.join(parts)}"


def merge_requirements(*maps: dict[str, int]) -> dict[str, int]:
    """Sum category mins across all degree components."""

    out: dict[str, int] = {}
    for m in maps:
        for cat, n in m.items():
            out[cat] = out.get(cat, 0) + int(n)
    return out


def resolve_requirements(plan: DegreePlan) -> dict[str, int]:
    """Build cumulative graduation requirements for a student's degree plan."""

    parts: list[dict[str, int]] = [MAJORS.get(plan.primary, MAJORS["CS-Major"])]
    for key in plan.specializations:
        parts.append(SPECIALIZATIONS.get(key, {}))
    for key in plan.minors:
        parts.append(MINORS.get(key, {}))
    for key in plan.extra_majors:
        parts.append(MAJORS.get(key, {}))
    return merge_requirements(*parts)


def language_category(residency: Residency | None) -> str:
    """Which catalog category satisfies the 1A language/English slot."""

    if residency == "international":
        return INTL_ENGLISH_CATEGORY
    return DOMESTIC_LANGUAGE_CATEGORY


def default_plan(primary_reqs_key: str) -> DegreePlan:
    return DegreePlan(kind="major", primary=primary_reqs_key or "CS-Major")


# --- NL parsing ------------------------------------------------------------- #
_RESIDENCY_INTL = (
    "international student", "intl student", "i'm international", "i am international",
    "study permit", "f1 visa", "f-1", "visa student", "esl", "ell", "english language learner",
    "not a native english", "non-native english", "from overseas", "overseas student",
)
_RESIDENCY_DOMESTIC = (
    "domestic student", "canadian citizen", "canadian student", "permanent resident",
    "pr card", "born in canada", "i'm domestic", "i am domestic", "not international",
)


def parse_residency(text: str) -> Residency | None:
    low = text.lower()
    if any(k in low for k in _RESIDENCY_INTL) or re.search(r"\binternational\b", low):
        return "international"
    if any(k in low for k in _RESIDENCY_DOMESTIC) or re.search(r"\bdomestic\b", low):
        return "domestic"
    if re.search(r"\b(yes|yeah|yep)\b", low) and "international" in low:
        return "international"
    if re.search(r"\b(no|nope)\b", low) and "international" in low:
        return "domestic"
    return None


_SPEC_PATTERNS: list[tuple[str, str]] = [
    (r"\bai spec(?:ialization)?\b|\bartificial intelligence spec", "CS-AI-Specialization"),
    (r"\bbusiness\s+spec\w*|\bbusiness specialization\b", "CS-Business-Specialization"),
    (r"\bcomputational math spec", "CS-Computational-Math-Specialization"),
    (r"\bhci spec|\bhuman-computer interaction spec", "CS-HCI-Specialization"),
    (r"\bgame design spec|\bgame spec|\bgames? specialization\b", "CS-Game-Design-Specialization"),
    (r"\bdigital hardware spec|\bhardware specialization\b", "CS-Digital-Hardware-Specialization"),
    (r"\bbioinformatics spec|\bbioinformatics specialization\b|\bcomputational biology\b", "CS-Bioinformatics-Specialization"),
    (r"\bcomputational fine art|\bfine art spec|\bcomputational art\b", "CS-Computational-Fine-Art-Specialization"),
    (r"\bspecializ(?:e|ing|ation) in ai\b", "CS-AI-Specialization"),
    (r"\bspecializ(?:e|ing|ation) in business\b|\bwant.*business\b", "CS-Business-Specialization"),
]

_MINOR_PATTERNS: list[tuple[str, str]] = [
    (r"\bstats minor\b|\bstatistics minor\b", "Stats-Minor"),
    (r"\bpure math(?:ematics)? minor\b|\bpmath minor\b", "PMath-Minor"),
    (r"\b(?:combinatorics|optimization|c\s*&\s*o|co) minor\b", "CO-Minor"),
    (r"\bmath minor\b|\bmathematics minor\b", "Math-Minor"),
    (r"\becon(?:omics)? minor\b", "Economics-Minor"),
    (r"\bpsych(?:ology)? minor\b", "Psych-Minor"),
]

_EXTRA_MAJOR_PATTERNS: list[tuple[str, str]] = [
    (r"\bmath major\b|\bmathematics major\b|\bdouble major.*math\b|\bmath.*double major\b", "Math-Major"),
    (r"\bdata science major\b|\bdouble major.*data\b", "DataScience-Major"),
]


def parse_degree_plan(text: str, primary_reqs_key: str) -> DegreePlan | None:
    """Infer degree structure from free text; return None if nothing new."""

    low = text.lower()
    if any(k in low for k in (
        "just the major", "just major", "major only", "honours only", "only the major",
        "no minor", "no specialization", "no spec",
    )):
        return default_plan(primary_reqs_key)

    specs: list[str] = []
    minors: list[str] = []
    extras: list[str] = []

    for pat, key in _SPEC_PATTERNS:
        if re.search(pat, low) and key not in specs:
            specs.append(key)
    for pat, key in _MINOR_PATTERNS:
        if re.search(pat, low) and key not in minors:
            minors.append(key)
    for pat, key in _EXTRA_MAJOR_PATTERNS:
        if re.search(pat, low) and key not in extras and key != primary_reqs_key:
            extras.append(key)

    triple = any(k in low for k in ("triple major", "three majors", "3 majors"))
    double = any(k in low for k in ("double major", "dual major", "two majors", "2 majors"))
    has_minor = bool(minors) or any(k in low for k in ("with a minor", " and a minor", "minor in"))
    has_spec = bool(specs) or any(
        k in low for k in ("specialization", "specialisation", "specilization", "specialize", "specialise")
    )

    if not (specs or minors or extras or triple or double or has_minor or has_spec):
        return None

    if triple and len(extras) >= 2:
        kind: DegreeKind = "triple_major"
    elif triple or (double and len(extras) >= 1):
        kind = "double_major" if extras else "double_major"
    elif minors:
        kind = "major_minor"
    elif specs or has_spec:
        kind = "major_specialization"
    elif double:
        kind = "double_major"
    else:
        kind = "major"

    return DegreePlan(
        kind=kind,
        primary=primary_reqs_key or "CS-Major",
        specializations=tuple(specs),
        minors=tuple(minors),
        extra_majors=tuple(extras),
    )


def plan_from_intake(intake: dict) -> DegreePlan:
    raw = intake.get("degree_plan")
    if isinstance(raw, dict) and raw.get("primary"):
        return DegreePlan(
            kind=raw.get("kind", "major"),
            primary=raw["primary"],
            specializations=tuple(raw.get("specializations") or ()),
            minors=tuple(raw.get("minors") or ()),
            extra_majors=tuple(raw.get("extra_majors") or ()),
        )
    return default_plan(intake.get("reqs_key", "CS-Major"))


def plan_to_dict(plan: DegreePlan) -> dict:
    return {
        "kind": plan.kind,
        "primary": plan.primary,
        "specializations": list(plan.specializations),
        "minors": list(plan.minors),
        "extra_majors": list(plan.extra_majors),
        "display": plan.display(),
    }
