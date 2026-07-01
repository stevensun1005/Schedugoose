"""Comprehensive UW degree-requirement knowledge base.

Curated from the University of Waterloo undergraduate calendar and the Cheriton
School of CS plan-requirement checklists — the majors, minors, and
specializations a student can pursue, with the courses / category counts each
adds. Two audiences:

- the **advisor / requirements Q&A** cites these (with sources), and
- the **planner** uses the ``category_reqs`` of the schedulable ones.

Course-schedulability is flagged: specializations that need subjects outside the
planner's course catalog (BIOL, FINE, ECE, …) are reference-only.

Sources:
- CS plans & specializations — https://cs.uwaterloo.ca/current-undergraduate-students/majors
- Plan requirement checklists — https://cs.uwaterloo.ca/checklists
- Undergraduate calendar — https://ucalendar.uwaterloo.ca
- Math minors — https://uwaterloo.ca/math/undergraduate-studies
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DegreeComponent:
    key: str
    name: str
    kind: str                # "major" | "minor" | "specialization"
    summary: str
    required_courses: list[str] = field(default_factory=list)   # all required
    one_of: list[list[str]] = field(default_factory=list)       # each inner list = choose one
    category_reqs: dict[str, int] = field(default_factory=dict)  # planner-facing extra minimums
    schedulable: bool = True   # False when it needs subjects outside our catalog
    source: str = "cs.uwaterloo.ca/checklists"


# --------------------------------------------------------------------------- #
# Majors
# --------------------------------------------------------------------------- #
MAJOR_INFO: dict[str, DegreeComponent] = {
    "CS-Major": DegreeComponent(
        "CS-Major", "Bachelor of Computer Science (Honours)", "major",
        "Core CS (CS 135/136, 240, 241, 245, 246, 251, 341, 350, 360), the math "
        "core (MATH 135/136/137/138/237/239), two STAT, communication, and CS "
        "electives at the 300/400 level.",
        category_reqs={"CS-Core": 8, "Math-Core": 6, "STAT-Core": 2, "Comm": 1,
                       "CS-3xx": 3, "CS-4xx": 4, "Elective": 8},
        source="cs.uwaterloo.ca/current-undergraduate-students/majors",
    ),
    "DataScience-Major": DegreeComponent(
        "DataScience-Major", "Data Science (Honours)", "major",
        "CS + statistics + machine learning: CS core, STAT 230/231/x, data-focused "
        "CS (CS 348/451/480/486), plus math.",
        category_reqs={"CS-Core": 5, "Math-Core": 3, "STAT-Core": 2, "STAT-ML": 1,
                       "CS-AI": 1, "Comm": 1, "Elective": 6},
        source="uwaterloo.ca/math/undergraduate-studies/programs/data-science",
    ),
}


# --------------------------------------------------------------------------- #
# CS specializations (add on top of the CS major)
# --------------------------------------------------------------------------- #
SPECIALIZATION_INFO: dict[str, DegreeComponent] = {
    "CS-AI-Specialization": DegreeComponent(
        "CS-AI-Specialization", "Artificial Intelligence", "specialization",
        "AI/ML depth. Required CS 486 and CS 492; one of CS 480 / CS 485; one "
        "control course (SE 380 / ECE 380); plus three approved AI electives "
        "(one Math, one Engineering).",
        required_courses=["CS 486", "CS 492"],
        one_of=[["CS 480", "CS 485"], ["SE 380", "ECE 380"]],
        category_reqs={"CS-AI": 2, "STAT-ML": 1, "CS-4xx": 1},
        source="ucalendar.uwaterloo.ca — MATH Computer Science Specializations",
    ),
    "CS-Business-Specialization": DegreeComponent(
        "CS-Business-Specialization", "Business", "specialization",
        "Business/entrepreneurship breadth on top of the CS major — communication "
        "plus business/economics electives (e.g. ECON 101, AFM, BET/ENBUS).",
        category_reqs={"Elective": 2, "Comm": 1},
        source="cs.uwaterloo.ca/checklists",
    ),
    "CS-HCI-Specialization": DegreeComponent(
        "CS-HCI-Specialization", "Human-Computer Interaction", "specialization",
        "Human-computer interaction — user interfaces and design (e.g. CS 349, "
        "CS 449, CS 489 HCI topics) plus a design/psychology elective.",
        required_courses=["CS 349"],
        category_reqs={"CS-3xx": 1, "Elective": 1},
        source="cs.uwaterloo.ca/checklists",
    ),
    "CS-Computational-Math-Specialization": DegreeComponent(
        "CS-Computational-Math-Specialization", "Computational Mathematics", "specialization",
        "Extra applied/continuous math and theory (numerical methods, optimization, "
        "combinatorics) — additional MATH/CO courses and a theory CS course.",
        category_reqs={"Math-Core": 2, "CS-Theory": 1},
        source="cs.uwaterloo.ca/checklists",
    ),
    "CS-Game-Design-Specialization": DegreeComponent(
        "CS-Game-Design-Specialization", "Game Design", "specialization",
        "Graphics, game design, and interaction — CS 488 (graphics), a game-design "
        "course, plus approved electives.",
        required_courses=["CS 488"],
        category_reqs={"CS-4xx": 1, "Elective": 1},
        source="cs.uwaterloo.ca/checklists",
    ),
    "CS-Digital-Hardware-Specialization": DegreeComponent(
        "CS-Digital-Hardware-Specialization", "Digital Hardware", "specialization",
        "Computer hardware/architecture — CS 251 plus ECE hardware courses. "
        "Competitive entry (apply in 1A, ~75% average).",
        required_courses=["CS 251"],
        category_reqs={"Elective": 2},
        schedulable=False,  # needs ECE courses outside the catalog
        source="cs.uwaterloo.ca/current-undergraduate-students/majors/computer-science-specializations",
    ),
    "CS-Bioinformatics-Specialization": DegreeComponent(
        "CS-Bioinformatics-Specialization", "Bioinformatics", "specialization",
        "Computational biology — BIOL 130/239/240/373, CS 482 (computational "
        "techniques for bioinformatics), plus biology electives.",
        required_courses=["CS 482"],
        schedulable=False,  # needs BIOL courses outside the catalog
        source="cs.uwaterloo.ca — BCS Bioinformatics Specialization checklist",
    ),
    "CS-Computational-Fine-Art-Specialization": DegreeComponent(
        "CS-Computational-Fine-Art-Specialization", "Computational Fine Art", "specialization",
        "Art + code — first-year studio (FINE 100/130), FINE studio electives, and "
        "graphics/HCI CS courses. Requires a plan-modification form.",
        schedulable=False,  # needs FINE courses outside the catalog
        source="cs.uwaterloo.ca/current-undergraduate-students/majors/computer-science-specializations",
    ),
}


# --------------------------------------------------------------------------- #
# Minors commonly paired with a CS/Math degree
# --------------------------------------------------------------------------- #
MINOR_INFO: dict[str, DegreeComponent] = {
    "Stats-Minor": DegreeComponent(
        "Stats-Minor", "Statistics Minor", "minor",
        "STAT 230/231 plus additional STAT (330/331/332/333/…) — usually ~5 STAT "
        "courses total, plus a supporting math course.",
        required_courses=["STAT 230", "STAT 231"],
        category_reqs={"STAT-Core": 3, "Math-Minor": 1},
        source="uwaterloo.ca/math/undergraduate-studies",
    ),
    "Math-Minor": DegreeComponent(
        "Math-Minor", "Mathematics Minor", "minor",
        "A breadth of math courses (algebra, analysis, combinatorics) — several "
        "MATH courses beyond the core.",
        category_reqs={"Math-Core": 4, "Math-Minor": 2},
        source="uwaterloo.ca/math/undergraduate-studies",
    ),
    "PMath-Minor": DegreeComponent(
        "PMath-Minor", "Pure Mathematics Minor", "minor",
        "Analysis and algebra depth (PMATH 333/347/348/351/…).",
        category_reqs={"Math-Core": 4},
        schedulable=False,  # needs PMATH courses outside the catalog
        source="uwaterloo.ca/pure-mathematics",
    ),
    "CO-Minor": DegreeComponent(
        "CO-Minor", "Combinatorics & Optimization Minor", "minor",
        "Discrete math and optimization (CO 250/342/351/…).",
        category_reqs={"Math-Core": 4},
        schedulable=False,  # needs CO courses beyond CO 487
        source="uwaterloo.ca/combinatorics-and-optimization",
    ),
    "Economics-Minor": DegreeComponent(
        "Economics-Minor", "Economics Minor", "minor",
        "ECON 101/102 plus intermediate micro/macro and electives.",
        required_courses=["ECON 101"],
        category_reqs={"Elective": 3},
        source="uwaterloo.ca/economics",
    ),
    "Psych-Minor": DegreeComponent(
        "Psych-Minor", "Psychology Minor", "minor",
        "PSYCH 101 plus additional psychology courses.",
        required_courses=["PSYCH 101"],
        category_reqs={"Elective": 3},
        source="uwaterloo.ca/psychology",
    ),
}


ALL_COMPONENTS: dict[str, DegreeComponent] = {
    **MAJOR_INFO, **SPECIALIZATION_INFO, **MINOR_INFO,
}


def describe_component(key: str) -> str | None:
    c = ALL_COMPONENTS.get(key)
    if not c:
        return None
    lines = [f"**{c.name}** ({c.kind})", c.summary]
    if c.required_courses:
        lines.append(f"Required: {', '.join(c.required_courses)}.")
    for group in c.one_of:
        lines.append(f"One of: {', '.join(group)}.")
    if c.category_reqs:
        extra = ", ".join(f"{k} ×{v}" for k, v in c.category_reqs.items())
        lines.append(f"Category minimums: {extra}.")
    if not c.schedulable:
        lines.append("(Needs subjects outside this planner's course data — reference only.)")
    lines.append(f"Source: {c.source}")
    return "\n".join(lines)


def list_components(kind: str | None = None) -> list[DegreeComponent]:
    return [c for c in ALL_COMPONENTS.values() if kind is None or c.kind == kind]
