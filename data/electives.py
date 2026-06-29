"""Easy / bird-course elective pool for the picker step."""

from __future__ import annotations

from data.uw_api import fetch_courses

EASY_THRESHOLD = 0.75


def easy_elective_options(completed: set[str] | None = None) -> list[dict[str, str]]:
    """Return eligible easy electives the user can choose from."""

    completed = completed or set()
    out: list[dict[str, str]] = []
    for c in fetch_courses():
        if c.course_id in completed:
            continue
        if "Elective" not in c.categories:
            continue
        if c.easiness < EASY_THRESHOLD:
            continue
        if c.course_id.upper().startswith("PD"):
            continue
        out.append({
            "course_id": c.course_id,
            "title": c.title,
            "easiness": str(round(c.easiness, 2)),
        })
    out.sort(key=lambda row: (-float(row["easiness"]), row["course_id"]))
    return out


def format_elective_menu(options: list[dict[str, str]], limit: int = 8) -> str:
    """Human-readable bullet list for the clarify question."""

    lines = []
    for row in options[:limit]:
        lines.append(f"  - {row['course_id']}: {row['title']}")
    return "\n".join(lines)
