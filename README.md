# 🪿 Schedugoose

A conversational course-planning agent that pairs an LLM with an OR-Tools
CP-SAT solver. See [`schedugoose-README.md`](./schedugoose-README.md) for the
full design write-up (architecture, data/optimization model, eval).

## Quick start

```bash
python -m venv venv && venv\Scripts\activate     # Windows
# source venv/bin/activate                          # macOS / Linux
pip install -e .

# 1) Verify the OR core first -- no API keys needed
python -m pytest tests/test_scheduler.py

# 2) Run the eval harness (constraint / intent / explanation axes)
python -m eval.run_eval

# 3) Run the API + chat UI
uvicorn app.main:app --reload
# open http://127.0.0.1:8000
```

Everything runs **offline with zero keys**: without `UW_API_KEY` it uses
bundled mock course data, and without `ANTHROPIC_API_KEY` the semantic and
explanation layers fall back to deterministic logic. Add keys in `.env`
(`cp .env.example .env`) to use the live UW Open Data API and Claude.

## How a conversation goes

Schedugoose plans your courses **term by term across your whole co-op
sequence**, starting from your 1A term. It runs a short guided onboarding,
asking only for what's missing:

1. **Program** — "I'm a first-year CS student" → identifies your faculty
   (Math / Engineering / Science) and degree requirements.
2. **Sequence / stream** — Engineering is lockstep (Stream 4 vs Stream 8);
   Math/Science offer Regular vs Co-op. It asks which one you're in.
3. **Start term** — e.g. "Fall 2026" (your 1A); the plan is built forward
   along the sequence, interleaving co-op work terms.
4. **Career + preferences** — "aiming for data science, keep it light, at
   least one easy course, no mornings". Then it plans every study term: 1A → 4B.

Each study term is an independent CP-SAT solve (conflict-free, within your
course-load, at least one easy course if asked); prerequisites unlock as earlier
terms complete; and courses are steered toward your still-unmet degree
requirements. Say "only 3 courses a term", "make it lighter", or "change my
sequence" and it re-plans.

## Layout

| Path | What |
|------|------|
| `scheduler/` | OR core: data model, conflict preprocessing, CP-SAT model, solve + infeasibility diagnosis (no LLM, unit-tested) |
| `data/` | UW API wrapper + normalization, 1A–4B mock catalog, program requirements, **co-op sequences + program identification**, RAG knowledge base, prereq pre-filtering |
| `agent/` | Orchestration: state, onboarding `intake`, multi-term `planner`, nodes (gather / clarify / plan_terms / explain), LangGraph graph + functional fallback |
| `app/` | FastAPI app, `/plan` + `/health`, session memory, chat UI |
| `eval/` | Machine-verifiable plan checker + multi-turn onboarding test cases |
| `tests/` | Scheduler unit tests |

## Design rule

The integer-programming core is the foundation: it's built and tested with mock
data, fully decoupled from the LLM. The LLM only **translates** natural language
into a structured solver config and **explains** the result — it never computes
the schedule.
