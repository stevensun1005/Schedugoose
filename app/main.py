"""FastAPI entrypoint.

Run with: ``uvicorn app.main:app --reload``
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

from app.routes import router  # noqa: E402

app = FastAPI(
    title="Schedugoose",
    description="Conversational course planning: LLM + OR-Tools CP-SAT.",
    version="0.1.0",
)
app.include_router(router)


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return _INDEX_HTML


_INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Schedugoose</title>
<style>
  :root { --bg:#0f1115; --panel:#171a21; --accent:#f5b301; --text:#e8eaed; --muted:#9aa0a6; }
  * { box-sizing:border-box; }
  body { margin:0; font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;
         background:var(--bg); color:var(--text); height:100vh; display:flex; flex-direction:column; }
  header { padding:16px 24px; border-bottom:1px solid #23262e; display:flex; align-items:center; gap:10px; }
  header h1 { font-size:18px; margin:0; font-weight:600; }
  header .tag { font-size:12px; color:var(--muted); }
  #chat { flex:1; overflow-y:auto; padding:24px; display:flex; flex-direction:column; gap:14px; max-width:860px; width:100%; margin:0 auto; }
  .msg { padding:12px 16px; border-radius:14px; max-width:80%; line-height:1.5; white-space:pre-wrap; }
  .user { align-self:flex-end; background:#2a3340; }
  .bot { align-self:flex-start; background:var(--panel); border:1px solid #23262e; }
  .sched { margin-top:10px; border-top:1px solid #2a2e37; padding-top:10px; display:grid; grid-template-columns:repeat(auto-fill,minmax(150px,1fr)); gap:8px; }
  .term { background:#0f1218; border:1px solid #2a2e37; border-radius:10px; padding:8px 10px; }
  .term.work { background:#14110a; border-color:#3a3320; }
  .term .hd { font-size:12px; font-weight:600; color:var(--accent); display:flex; justify-content:space-between; }
  .term .hd .yr { color:var(--muted); font-weight:400; }
  .term ul { margin:6px 0 0; padding-left:16px; }
  .term li { font-size:12px; color:var(--text); padding:1px 0; }
  .term .note { font-size:11px; color:var(--muted); margin-top:4px; font-style:italic; }
  .term .wlabel { font-size:12px; color:var(--muted); margin-top:4px; }
  form { display:flex; gap:10px; padding:16px 24px; border-top:1px solid #23262e; max-width:860px; width:100%; margin:0 auto; }
  input { flex:1; padding:12px 14px; border-radius:10px; border:1px solid #2a2e37; background:#0c0e12; color:var(--text); font-size:14px; }
  button { padding:12px 18px; border-radius:10px; border:none; background:var(--accent); color:#1a1a1a; font-weight:600; cursor:pointer; }
  button:disabled { opacity:.5; cursor:default; }
</style>
</head>
<body>
<header>
  <span style="font-size:22px">&#129446;</span>
  <h1>Schedugoose</h1>
  <span class="tag">LLM + OR-Tools course planner</span>
</header>
<div id="chat"></div>
<form id="f">
  <input id="m" autocomplete="off"
    placeholder="e.g. I'm a first-year CS student aiming for data science, keep it light"/>
  <button id="send" type="submit">Plan</button>
</form>
<script>
let sessionId = null;
const chat = document.getElementById('chat');
const form = document.getElementById('f');
const input = document.getElementById('m');
const btn = document.getElementById('send');

// First-year by default (empty transcript). Returning students could pass
// their completed courses here.
const profile = { completed: [] };

function bubble(text, who) {
  const d = document.createElement('div');
  d.className = 'msg ' + who;
  d.textContent = text;
  chat.appendChild(d);
  chat.scrollTop = chat.scrollHeight;
  return d;
}

function renderPlan(bubbleEl, plan) {
  if (!plan || !plan.terms) return;
  const box = document.createElement('div');
  box.className = 'sched';
  for (const t of plan.terms) {
    const card = document.createElement('div');
    card.className = 'term' + (t.kind === 'work' ? ' work' : '');
    let inner = `<div class="hd"><span>${t.label}</span><span class="yr">${t.display}</span></div>`;
    if (t.kind === 'work') {
      inner += `<div class="wlabel">Co-op work term</div>`;
    } else if (t.courses && t.courses.length) {
      inner += '<ul>' + t.courses.map(c => `<li>${c}</li>`).join('') + '</ul>';
    } else {
      inner += `<div class="wlabel">open electives</div>`;
    }
    if (t.note) inner += `<div class="note">${t.note}</div>`;
    card.innerHTML = inner;
    box.appendChild(card);
  }
  bubbleEl.appendChild(box);
}

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  const text = input.value.trim();
  if (!text) return;
  bubble(text, 'user');
  input.value = '';
  btn.disabled = true;
  const thinking = bubble('Planning...', 'bot');
  try {
    const res = await fetch('/plan', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ message:text, session_id:sessionId, profile })
    });
    const data = await res.json();
    sessionId = data.session_id;
    thinking.textContent = data.explanation;
    renderPlan(thinking, data.plan);
  } catch (err) {
    thinking.textContent = 'Error: ' + err;
  } finally {
    btn.disabled = false;
    input.focus();
  }
});

bubble("Hi! I'll plan your courses term-by-term across your whole co-op "
     + "sequence. To start, tell me your program (for example: I am a "
     + "first-year CS student) and what you're aiming for. I'll then ask about "
     + "your sequence and start term, and build the plan from 1A onward.", 'bot');
</script>
</body>
</html>"""
