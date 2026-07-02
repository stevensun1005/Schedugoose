"""Resolve subject abbreviations / spoken names to UW subject codes.

The full code list mirrors the UW undergraduate calendar's subject index
(ucalendar.uwaterloo.ca / Open Data API `/subjects`). Codes change rarely, so
bundling them is a naming dictionary, not requirement data. Aliases cover what
students actually type ("no psychology in 1A", "avoid biology").
"""

from __future__ import annotations

from data.mock_data import MOCK_ROWS
from data.uw_api import fetch_courses

# Every UW undergraduate subject code (calendar subject index).
SUBJECT_CODES: frozenset[str] = frozenset({
    "ACTSC", "AFM", "AMATH", "ANTH", "APPLS", "ARABIC", "ARBUS", "ARCH",
    "ARTS", "ASL", "AVIA", "BASE", "BET", "BIOL", "BLKST", "BME", "BUS",
    "CDNST", "CFM", "CHE", "CHEM", "CHINA", "CIVE", "CLAS", "CMW", "CO",
    "COMMST", "CROAT", "CS", "DAC", "DUTCH", "EARTH", "EASIA", "ECE", "ECON",
    "EMLS", "ENBUS", "ENGL", "ENVE", "ENVS", "ERS", "FINE", "FR", "GBDA",
    "GENE", "GEOE", "GEOG", "GER", "GERON", "GRK", "GSJ", "HEALTH", "HIST",
    "HLTH", "HRM", "HRTS", "HUMSC", "INDEV", "INDG", "INTEG", "INTST",
    "ITAL", "ITALST", "JAPAN", "JS", "KIN", "KOREA", "LAT", "LS", "MATBUS",
    "MATH", "ME", "MEDVL", "MGMT", "MNS", "MOHAWK", "MSE", "MSCI", "MTE",
    "MTHEL", "MUSIC", "NE", "OPTOM", "PACS", "PD", "PDARCH", "PHARM", "PHIL",
    "PHYS", "PLAN", "PMATH", "PSCI", "PSYCH", "REC", "RS", "RUSS", "SCBUS",
    "SCI", "SDS", "SE", "SI", "SMF", "SOC", "SOCWK", "SPAN", "SPCOM", "STAT",
    "STV", "SYDE", "THPERF", "UNIV", "VCULT", "WKRPT",
})

# Spoken names / shorthands → UW subject codes. Identity mappings are implied
# (any code in SUBJECT_CODES normalizes to itself).
_SUBJECT_ALIASES: dict[str, str] = {
    # arts & humanities
    "ENGLISH": "ENGL",
    "PHILOSOPHY": "PHIL",
    "HISTORY": "HIST",
    "CLASSICS": "CLAS",
    "RELIGION": "RS",
    "MUSI": "MUSIC",
    "MUS": "MUSIC",
    "DRAMA": "THPERF",
    "THEATRE": "THPERF",
    "THEATER": "THPERF",
    # social sciences
    "ECONOMICS": "ECON",
    "PSYCHOLOGY": "PSYCH",
    "PSYCHO": "PSYCH",
    "SOCIOLOGY": "SOC",
    "ANTHROPOLOGY": "ANTH",
    "ANTHRO": "ANTH",
    "GEOGRAPHY": "GEOG",
    "POLITICS": "PSCI",
    "POLISCI": "PSCI",
    "LEGAL": "LS",
    "LAW": "LS",
    # math faculty
    "STATS": "STAT",
    "STATISTICS": "STAT",
    "ACTUARIAL": "ACTSC",
    "COMBINATORICS": "CO",
    "OPTIMIZATION": "CO",
    "PUREMATH": "PMATH",
    "APPLIEDMATH": "AMATH",
    "COMPSCI": "CS",
    "COMPUTERSCIENCE": "CS",
    # sciences & health
    "BIO": "BIOL",
    "BIOLOGY": "BIOL",
    "CHEMISTRY": "CHEM",
    "PHYSICS": "PHYS",
    "KINESIOLOGY": "KIN",
    "GERONTOLOGY": "GERON",
    "PHARMACY": "PHARM",
    "OPTOMETRY": "OPTOM",
    "NANO": "NE",
    # environment / planning / business
    "ENVIRONMENT": "ENVS",
    "PLANNING": "PLAN",
    "ACCOUNTING": "AFM",
    "FINANCE": "AFM",
    "BUSINESS": "BUS",
    "MANAGEMENT": "MGMT",
    "MARKETING": "MGMT",
    "RECREATION": "REC",
    "SOCIALWORK": "SOCWK",
    "ARCHITECTURE": "ARCH",
    # languages
    "FRENCH": "FR",
    "GERMAN": "GER",
    "SPANISH": "SPAN",
    "ITALIAN": "ITAL",
    "JAPANESE": "JAPAN",
    "CHINESE": "CHINA",
    "MANDARIN": "CHINA",
    "KOREAN": "KOREA",
    "RUSSIAN": "RUSS",
    "LATIN": "LAT",
    "GREEK": "GRK",
    "CROATIAN": "CROAT",
    "COMMUNICATION": "COMMST",
    "COMMUNICATIONS": "COMMST",
}


def normalize_subject(subject: str) -> str:
    key = subject.strip().upper().replace(" ", "")
    if key in SUBJECT_CODES:
        return key
    return _SUBJECT_ALIASES.get(key, key)


def is_known_subject(subject: str) -> bool:
    return normalize_subject(subject) in SUBJECT_CODES


def course_ids_for_subject(subject: str) -> list[str]:
    """All catalog course ids for a subject, e.g. ENGL → ENGL 119, ENGL 129."""

    subj = normalize_subject(subject)
    prefix = f"{subj} "
    ids: list[str] = []
    seen: set[str] = set()

    for row in MOCK_ROWS:
        cid = row["course_id"]
        if cid.startswith(prefix) and cid not in seen:
            ids.append(cid)
            seen.add(cid)

    try:
        for course in fetch_courses():
            if course.course_id.startswith(prefix) and course.course_id not in seen:
                ids.append(course.course_id)
                seen.add(course.course_id)
    except Exception:
        pass

    return ids
