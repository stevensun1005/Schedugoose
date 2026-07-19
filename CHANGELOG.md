# Changelog

Bug-fix log (newest first). Every fix is verified by a regression test and,
where the bug only reproduced with a live LLM / live UW data, against the
running server — the offline eval cannot catch live-only failures.

## Correctness — planner & requirements

- **Enrolled courses after a plan were silently ignored** — the standing /
  transcript capture only ran during onboarding, so the 📅 schedule-sync and
  "I'm currently enrolled in …" did nothing once a plan existed. Now they
  merge into the transcript and trigger a re-plan. (`a4c6914`+)
- **Prereq alternatives** — "CS 136 or CS 146" was flattened to the first
  option; advanced-stream (CS 146 / MATH 148) and transfer students were
  wrongly filtered out of everything downstream. Prereqs are AND-of-OR trees
  now, and every eligibility check routes through one function. (`dde5ae7`)
- **Live UW data was silently broken** — a refactor dropped the `get_or_set`
  import; every live fetch raised `NameError` inside a `try/except` and fell
  back to mock (exactly why `/health` always said `live+mock-fallback`).
  Found by adding ruff to CI. (`f5aa5af`)
- **Antireqs / program restrictions unenforced for real families** — a Math
  Studies student was scheduled MATH 235/247 despite having MATH 225/237
  (antirequisites), and CS-major-only courses (CS 240+) leaked into non-CS
  plans. Data added; prefilter already enforced it. (`ff3b970`)
- **Failed courses counted as completed** — a blind course-code sweep over a
  Quest transcript marked failed attempts (earned 0.00) as done, so the
  planner skipped courses still needed; retakes now win, in-progress rows are
  tracked separately. The same transcript also exposed that Quest's
  double-spaced codes ("CS  135") didn't parse at all. (`5fb248f`)
- **"Heavier" terms overshot the degree** — marking every term heavier
  produced a 42-course / 21-credit plan; heavy is now capped by remaining
  credits. (`375c80a`) Related: the final-term credit cap could demand an
  unreachable 0.75 credits and leave the degree short (`ec30b22`), and a
  requirement-covering course could lose to an easier filler on near-tied
  objectives (`c4a9689`).
- **Wrong sub-plan resolved** — "business specialization" for a Mathematical
  Studies student returned the CS one; sub-plans share titles and differ only
  by code prefix (MS-/CS-), and the Kuali search truncated before the right
  entry. Ranking is now program-context-aware. (`bad9afb`)
- **Sequence-chart drift** — the curated "when is X normally taken" table
  disagreed with the official SCS charts on four courses (MATH 239, STAT 231,
  CS 341, CS 360); transcribed the five official 2022-23 chart PDFs and
  regenerated. (`4c66f3b`)

## Correctness — LLM grounding (anti-hallucination)

- **Free-enumeration narrative removed** — the general explain prompt let a
  small model list a specialization's courses from its own knowledge,
  inventing codes and titles ("CS 442: Machine Learning"). Only one
  constrained free-text LLM path remains; everything that lists courses is
  rendered from plan/catalog/cited data. (`e69358d`)
- **Ineligible recommendations** — advisory pitched CS 486/CS 480 to a Math
  Studies student (CS-only; prereq failed). Every recommendation path now
  passes the solver's eligibility gates, and LLM replies are post-hoc
  checked: naming a course outside the eligible set discards the text.
  The actual leak turned out to be a deterministic electives list, not the
  LLM. (`8b497bc`)
- **Invented careers** — replies claimed "data science" goals the user never
  stated; career text never falls back to the raw message, profile-change
  turns render the grounded template, and the plan intro is discarded if it
  mentions a course code or calls UW "University of Washington". (`7566f55`,
  `ebf071d`)
- **Stale `replanned` regression** — declaring per-turn flags in the state
  schema (needed for LangGraph) made them persist across turns, so every
  later message re-dumped the full plan. Flags reset at the request boundary
  and are excluded from session persistence. LangGraph silently drops
  undeclared state keys — the same root cause had earlier made routing differ
  between the LangGraph and functional paths. (`d2c0f98`)

## Correctness — parsing & UI

- **Chat UI script was dead** — a template fix left a real newline inside a
  JS string literal (`join('` ⏎ `')`), a load-time `SyntaxError` that killed
  every button; invalid Python escapes in the inline JS regexes also spammed
  `SyntaxWarning`. (this release)
- **AES-encrypted Quest PDFs** failed with "cryptography required" — Quest
  exports are AES-encrypted with an empty user password. (`2d5a349`)
- **"add PHIL 145 to 3B" was a no-op** — the term-pin parser only accepted
  "in/for", and before that the message was misrouted as a course lookup.
  (`cf6555e`, `a7f31c9`) "swap X for Y" had no offline parser at all
  (`8134f69`); "make 5A lighter" silently re-dumped the plan instead of
  clarifying the valid term range (`5f7a065`).
- **Returning students started at 1A** — "going into 2B" / "im a 4th year
  student" produced a full 1A–4B plan with electives stuffed into "1A";
  the plan now starts at the actual entering term, and the standing regex
  tolerates words in between ("2A CS student"). (`2a0b9ce`, `ea3c967`)
- **Subject aliases were 8 entries** — "no psychology in 1A" couldn't
  resolve; the full UW subject index (~110 codes) plus ~60 spoken aliases
  now back it, and the invented mock code FREN was corrected to FR.
  (`ad35ecd`)
- **.ics events on statutory holidays** — weekly recurrences landed on
  Victoria Day / Canada Day; rule-defined Ontario holidays are excluded via
  EXDATE. Browser copy variance (tab-separated Quest rows) also parses now.
  (`bb92f55`, `a4c6914`)

## Notable non-bugs (deliberate decisions)

- Planned-term .ics export was **rejected**: the UW /Terms API exposes
  administrative term boundaries, not lecture dates — exporting would invent
  class days inside exam period. Only the Quest paste carries real dates.
- The bundled catalog carries **no term-offering data** and none is invented;
  the offering filter activates only with live data.
