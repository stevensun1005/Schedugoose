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
  header .llm-ok { color:#6dd58c; }
  header .llm-off { color:#f28b82; }
  #chat { flex:1; overflow-y:auto; padding:24px; display:flex; flex-direction:column; gap:14px; max-width:860px; width:100%; margin:0 auto; }
  .msg { padding:12px 16px; border-radius:14px; max-width:80%; line-height:1.5; white-space:pre-wrap; }
  .user { align-self:flex-end; background:#2a3340; }
  .bot { align-self:flex-start; background:var(--panel); border:1px solid #23262e; }
  .bot.err { background:#221518; border-color:#4a2d35; color:#f28b82; }
  .fb { margin-top:8px; display:flex; gap:6px; font-size:12px; color:var(--muted); }
  .fb button { background:#0f1218; border:1px solid #2a2e37; color:var(--text); border-radius:8px;
               padding:2px 8px; font-size:13px; cursor:pointer; }
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
  #upload { background:#0c0e12; border:1px solid #2a2e37; color:var(--text); font-size:16px; padding:12px 14px; }
  .ai-badge { margin-top:10px; font-size:11px; display:inline-flex; gap:6px; align-items:center;
              padding:4px 9px; border-radius:8px; line-height:1.3; }
  .ai-badge .dot { width:7px; height:7px; border-radius:50%; flex-shrink:0; }
  .ai-badge.full { background:#152218; color:#6dd58c; border:1px solid #2d4a38; }
  .ai-badge.full .dot { background:#6dd58c; }
  .ai-badge.partial { background:#221f14; color:#e8c547; border:1px solid #3d3820; }
  .ai-badge.partial .dot { background:#e8c547; }
  .ai-badge.rules { background:#221518; color:#f28b82; border:1px solid #4a2d35; }
  .ai-badge.rules .dot { background:#f28b82; }
</style>
</head>
<body>
<header>
  <span style="font-size:22px">&#129446;</span>
  <h1>Schedugoose</h1>
  <span class="tag" id="llm-status">checking LLM...</span>
</header>
<div id="chat"></div>
<form id="f">
  <input type="file" id="tfile" accept=".pdf,.txt,.csv,text/plain,application/pdf" style="display:none"/>
  <button type="button" id="upload" title="Upload your transcript (PDF or text) — I'll detect your completed courses">&#128206;</button>
  <input id="m" autocomplete="off"
    placeholder="e.g. I'm a first-year CS student aiming for data science, keep it light"/>
  <button id="send" type="submit">Plan</button>
</form>
<script>
let sessionId = localStorage.getItem('schedugoose_session');
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

function renderAiBadge(bubbleEl, data) {
  const understood = !!data.llm_understood;
  const explained = !!data.llm_explained;
  const configured = !!data.llm_configured;
  const parseFailed = !!data.llm_parse_failed;
  const offline = !!data.llm_offline;

  let cls = 'rules';
  let label = 'Rules only — no Groq this turn';
  if (!configured) {
    cls = 'rules';
    label = 'No GROQ_API_KEY loaded — restart server after editing .env';
  } else if (parseFailed || offline) {
    cls = 'rules';
    label = 'Groq could not parse this turn — rules + template (quota or model)';
  } else if (understood && explained) {
    cls = 'full';
    label = 'AI understood your message and wrote this reply';
  } else if (understood) {
    cls = 'partial';
    label = 'AI understood your message · reply text is template (quota fallback)';
  } else if (explained) {
    cls = 'partial';
    label = 'AI wrote this reply · intent parsed with rules';
  } else if (data.used_llm) {
    cls = 'full';
    label = 'AI used this turn';
  }

  const badge = document.createElement('div');
  badge.className = 'ai-badge ' + cls;
  badge.innerHTML = '<span class="dot"></span><span>' + label + '</span>';
  bubbleEl.appendChild(badge);
}

function renderFeedback(bubbleEl) {
  const bar = document.createElement('div');
  bar.className = 'fb';
  for (const [label, reward] of [['👍', 1], ['👎', -1]]) {
    const b = document.createElement('button');
    b.type = 'button'; b.textContent = label;
    b.onclick = () => {
      fetch('/feedback', { method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({ session_id: sessionId, reward }) }).catch(() => {});
      bar.textContent = 'Thanks for the feedback!';
    };
    bar.appendChild(b);
  }
  bubbleEl.appendChild(bar);
}

// Transcript upload (UWFlow-style): extract completed courses from a PDF/text
// file, then send them through the normal chat flow so the LLM plans around them.
const fileInput = document.getElementById('tfile');
document.getElementById('upload').addEventListener('click', () => fileInput.click());
fileInput.addEventListener('change', async () => {
  const file = fileInput.files[0];
  fileInput.value = '';
  if (!file) return;
  const note = bubble('Reading your transcript (' + file.name + ')…', 'bot');
  try {
    const fd = new FormData();
    fd.append('file', file);
    const res = await fetch('/transcript', { method: 'POST', body: fd });
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || 'Could not read that file.');
    let noteText = 'Found ' + data.courses.length + ' courses in your transcript';
    if (data.in_progress && data.in_progress.length)
      noteText += ' (' + data.in_progress.length + ' in progress)';
    if (data.failed && data.failed.length)
      noteText += '. Excluded failed attempts: ' + data.failed.join(', ');
    note.textContent = noteText + '.';
    // Failed codes stay OUT of the message so they aren't claimed as completed.
    let msg = 'Here is my transcript — ';
    if (data.program) msg += "I'm in " + data.program + ', ';
    if (data.level) msg += 'currently in my ' + data.level + ' term. ';
    msg += 'I have already completed or am currently taking: ' + data.courses.join(', ');
    input.value = msg;
    form.requestSubmit();
  } catch (err) {
    note.textContent = '⚠️ ' + err.message;
    note.classList.add('err');
  }
});

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  const text = input.value.trim();
  if (!text) return;
  bubble(text, 'user');
  input.value = '';
  btn.disabled = true;
  const thinking = bubble('Working on it…', 'bot');
  // Building a full plan hits the live UW API + LLM and can take ~15s; give it room.
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 120000);
  try {
    const res = await fetch('/plan', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ message:text, session_id:sessionId, profile }),
      signal: controller.signal
    });
    if (!res.ok) {
      const detail = await res.text().catch(() => '');
      throw new Error('Server returned ' + res.status + (detail ? ': ' + detail.slice(0, 200) : ''));
    }
    const data = await res.json();
    sessionId = data.session_id;
    localStorage.setItem('schedugoose_session', sessionId);
    thinking.textContent = data.explanation || '(no reply)';
    renderAiBadge(thinking, data);
    renderPlan(thinking, data.plan);
    renderFeedback(thinking);
  } catch (err) {
    let msg;
    if (err.name === 'AbortError') {
      msg = '⏱️ That timed out. The first plan can be slow (live course data) — please try again.';
    } else if (err instanceof TypeError) {
      msg = "⚠️ Couldn't reach the server. Make sure it's still running "
          + "(uvicorn app.main:app --reload) and reload this page, then try again.";
    } else {
      msg = '⚠️ ' + err.message;
    }
    thinking.textContent = msg;
    thinking.classList.add('err');
    input.value = text;  // keep the message so it can be resent
  } finally {
    clearTimeout(timer);
    btn.disabled = false;
    input.focus();
  }
});

bubble("Hey! I'm Schedugoose — I help UW students plan courses term-by-term across co-op. "
     + "Tell me about yourself in plain language (program, goals, preferences). "
     + "Are you a brand-new first-year, or returning? If you've already taken courses, "
     + "list them (e.g. CS 135, MATH 135) or upload your transcript with \\uD83D\\uDCCE and "
     + "I'll plan around them.", 'bot');

fetch('/health').then(r => r.json()).then(h => {
  const el = document.getElementById('llm-status');
  if (h.llm) {
    el.textContent = 'LLM: ' + h.llm_mode + ' | UW data: ' + (h.uw_data_source || '?');
    el.className = 'tag llm-ok';
  } else {
    el.textContent = 'LLM offline — add GROQ_API_KEY to .env (free at console.groq.com)';
    el.className = 'tag llm-off';
  }
}).catch(() => {
  document.getElementById('llm-status').textContent = 'LLM status unknown';
});
</script>
</body>
</html>"""
