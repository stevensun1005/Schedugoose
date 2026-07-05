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
  .bot code { background:#0c0e12; border:1px solid #2a2e37; border-radius:5px; padding:1px 5px; font-size:12px; }
  .bot a { color:var(--accent); }
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
  #upload, #ics { background:#0c0e12; border:1px solid #2a2e37; color:var(--text); font-size:16px; padding:12px 14px; }
  #ics-modal { position:fixed; inset:0; background:rgba(0,0,0,.55); display:none;
               align-items:center; justify-content:center; z-index:10; }
  #ics-modal .box { background:var(--panel); border:1px solid #2a2e37; border-radius:14px;
                    padding:18px; width:min(680px, 92vw); }
  #ics-modal textarea { width:100%; height:220px; background:#0c0e12; color:var(--text);
                        border:1px solid #2a2e37; border-radius:10px; padding:10px; font-size:12px; }
  #ics-modal .row { display:flex; gap:8px; justify-content:flex-end; margin-top:10px; }
  #ics-modal .hint { font-size:12px; color:var(--muted); margin:0 0 8px; }
  .tt { margin-top:10px; border-top:1px solid #2a2e37; padding-top:10px; }
  .tt-title { font-size:12px; color:var(--muted); margin-bottom:6px; }
  .tt-grid { display:flex; gap:4px; }
  .tt-col { flex:1; position:relative; background:#0c0e12; border:1px solid #2a2e37; border-radius:8px; }
  .tt-day { text-align:center; font-size:11px; color:var(--muted); padding:2px 0; }
  .tt-block { position:absolute; left:3px; right:3px; border-radius:5px; font-size:9.5px;
              padding:1px 3px; overflow:hidden; color:#e8eaed; border:1px solid rgba(255,255,255,.12); }
  .dl { background:#0f1218; border:1px solid #2a2e37; color:var(--muted); border-radius:8px;
        padding:2px 8px; font-size:12px; cursor:pointer; }
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
  <button type="button" id="ics" title="Paste your Quest class schedule — download it as an .ics calendar with real rooms">&#128197;</button>
  <input id="m" autocomplete="off"
    placeholder="e.g. I'm a first-year CS student aiming for data science, keep it light"/>
  <button id="send" type="submit">Plan</button>
</form>
<div id="ics-modal">
  <div class="box">
    <p class="hint">Paste Quest → My Class Schedule (List View) below — I'll turn it into an
    .ics calendar with the real rooms (e.g. QNC 2501) as the event location. TBA/online rows are skipped.</p>
    <textarea id="ics-text" placeholder="CO 327 - Deter OR Models&#10;...&#10;MW 1:00PM - 2:20PM&#10;QNC 2501&#10;..."></textarea>
    <div class="row">
      <button type="button" class="dl" id="ics-cancel">cancel</button>
      <button type="button" id="ics-go">Download .ics</button>
    </div>
  </div>
</div>
<script>
let sessionId = localStorage.getItem('schedugoose_session');
const chat = document.getElementById('chat');
const form = document.getElementById('f');
const input = document.getElementById('m');
const btn = document.getElementById('send');

// First-year by default (empty transcript). Returning students could pass
// their completed courses here.
const profile = { completed: [] };
let pendingTranscript = null;   // parsed transcript to send with the next /plan

// Minimal, safe markdown for bot replies: escape everything first, then add
// back only our own tags (**bold**, `code`, auto-linked URLs).
function esc(s) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
function md(s) {
  let h = esc(s);
  h = h.replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>');
  h = h.replace(/`([^`]+)`/g, '<code>$1</code>');
  h = h.replace(/(https?:\/\/[^\s<)]+)/g, '<a href="$1" target="_blank" rel="noopener">$1</a>');
  return h;
}
function setBotText(el, text) { el.innerHTML = md(text); }

function bubble(text, who) {
  const d = document.createElement('div');
  d.className = 'msg ' + who;
  if (who === 'bot') setBotText(d, text); else d.textContent = text;
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
    if (t.why) inner += `<div class="note">why: ${t.why}</div>`;
    card.innerHTML = inner;
    box.appendChild(card);
  }
  bubbleEl.appendChild(box);
}

// Weekly timetable for the first study term that has section times — real
// UW schedules when published (live mode), representative times otherwise.
function renderTimetable(bubbleEl, plan) {
  const t = ((plan && plan.terms) || []).find(x => x.kind === 'study' && x.sections && x.sections.length);
  if (!t) return;
  function expandDays(str) {
    const out = []; let i = 0;
    while (i < (str || '').length) {
      const two = str.slice(i, i + 2);
      if (two === 'Th' || two === 'TH') { out.push('Th'); i += 2; }
      else if (str[i] === 'R') { out.push('Th'); i += 1; }
      else if ('MTWFS'.includes(str[i])) { out.push(str[i]); i += 1; }
      else i += 1;
    }
    return out;
  }
  const days = ['M', 'T', 'W', 'Th', 'F'];
  const startH = 8, endH = 20, pxPerMin = 0.6;
  const box = document.createElement('div');
  box.className = 'tt';
  box.innerHTML = '<div class="tt-title">Weekly timetable — ' + t.label + ' (' + t.display + ')</div>';
  const grid = document.createElement('div');
  grid.className = 'tt-grid';
  const colors = ['#2d4a38', '#3d3820', '#243447', '#4a2d35', '#3a2d4a', '#2d474a', '#47412d'];
  const colorOf = {}; let ci = 0;
  for (const d of days) {
    const col = document.createElement('div');
    col.className = 'tt-col';
    col.style.height = ((endH - startH) * 60 * pxPerMin + 20) + 'px';
    col.innerHTML = '<div class="tt-day">' + d + '</div>';
    for (const sec of t.sections) {
      for (const tm of (sec.times || [])) {
        if (!expandDays(tm.weekdays).includes(d)) continue;
        const [sh, sm] = String(tm.start).split(':').map(Number);
        const [eh, em] = String(tm.end).split(':').map(Number);
        if (isNaN(sh) || isNaN(eh)) continue;
        if (!(sec.course_id in colorOf)) colorOf[sec.course_id] = colors[ci++ % colors.length];
        const b = document.createElement('div');
        b.className = 'tt-block';
        b.style.top = (((sh * 60 + sm) - startH * 60) * pxPerMin + 20) + 'px';
        b.style.height = Math.max(14, ((eh * 60 + em) - (sh * 60 + sm)) * pxPerMin - 2) + 'px';
        b.style.background = colorOf[sec.course_id];
        b.title = sec.course_id + ' ' + sec.section_code + ' ' + tm.start + '–' + tm.end;
        b.textContent = sec.course_id.replace(' ', '') + (sec.component !== 'LEC' ? '·' + sec.component : '');
        col.appendChild(b);
      }
    }
    grid.appendChild(col);
  }
  box.appendChild(grid);
  bubbleEl.appendChild(box);
}

function renderDownload(bar, plan, explanation) {
  if (!plan || !plan.terms) return;
  const b = document.createElement('button');
  b.type = 'button'; b.className = 'dl'; b.textContent = '⬇ save plan';
  b.onclick = () => {
    const lines = ['Schedugoose plan — ' + (plan.program || '') + ' (' + (plan.start_term || '') + ')', ''];
    for (const t of plan.terms) {
      if (t.kind === 'work') lines.push(t.label + ' (' + t.display + '): co-op work term');
      else lines.push(t.label + ' (' + t.display + '): ' + (t.courses || []).join(', '));
      if (t.why) lines.push('    why: ' + t.why);
    }
    lines.push('', explanation || '');
    const blob = new Blob([lines.join('\n')], { type: 'text/plain' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'schedugoose-plan.txt';
    a.click();
    URL.revokeObjectURL(a.href);
  };
  bar.appendChild(b);
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
    label = 'AI understood · facts shown verbatim (grounded, no paraphrase)';
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

function renderFeedback(bubbleEl, plan, explanation) {
  const bar = document.createElement('div');
  bar.className = 'fb';
  renderDownload(bar, plan, explanation);
  for (const [label, reward] of [['👍', 1], ['👎', -1]]) {
    const b = document.createElement('button');
    b.type = 'button'; b.textContent = label;
    b.onclick = () => {
      // A thumbs-down with a reason is the most useful training signal.
      let note = null;
      if (reward < 0) note = window.prompt('What went wrong? (optional)') || null;
      fetch('/feedback', { method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({ session_id: sessionId, reward, note }) }).catch(() => {});
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
    if (data.program) noteText += ' — ' + data.program + (data.level ? ', ' + data.level : '');
    if (data.in_progress && data.in_progress.length)
      noteText += ' (' + data.in_progress.length + ' in progress)';
    if (data.failed && data.failed.length)
      noteText += '. Excluded failed attempts: ' + data.failed.join(', ');
    note.textContent = noteText + '.';
    // The parsed transcript rides along on the request and pre-fills the whole
    // intake server-side (program, level, next term, completed) — no wall of
    // codes in the chat, no re-asking questions the transcript answers.
    pendingTranscript = data;
    profile.completed = data.courses;
    input.value = 'Here is my transcript — plan my remaining terms.';
    form.requestSubmit();
  } catch (err) {
    note.textContent = '⚠️ ' + err.message;
    note.classList.add('err');
  }
});

// Quest schedule -> .ics with real rooms as LOCATION.
const icsModal = document.getElementById('ics-modal');
document.getElementById('ics').addEventListener('click', () => { icsModal.style.display = 'flex'; });
document.getElementById('ics-cancel').addEventListener('click', () => { icsModal.style.display = 'none'; });
document.getElementById('ics-go').addEventListener('click', async () => {
  const text = document.getElementById('ics-text').value.trim();
  if (!text) return;
  try {
    const res = await fetch('/schedule.ics', { method: 'POST',
      headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text }) });
    if (!res.ok) { alert(await res.text()); return; }
    const blob = await res.blob();
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'uw-schedule.ics';
    a.click();
    URL.revokeObjectURL(a.href);
    icsModal.style.display = 'none';
    bubble("Your schedule calendar is downloading — import uw-schedule.ics into Google/Outlook/Apple Calendar. Rooms are set as each event's location.", 'bot');
  } catch (err) { alert('Could not reach the server: ' + err.message); }
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
    const body = { message:text, session_id:sessionId, profile };
    if (pendingTranscript) { body.transcript = pendingTranscript; pendingTranscript = null; }
    const res = await fetch('/plan', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify(body),
      signal: controller.signal
    });
    if (!res.ok) {
      const detail = await res.text().catch(() => '');
      throw new Error('Server returned ' + res.status + (detail ? ': ' + detail.slice(0, 200) : ''));
    }
    const data = await res.json();
    sessionId = data.session_id;
    localStorage.setItem('schedugoose_session', sessionId);
    setBotText(thinking, data.explanation || '(no reply)');
    renderAiBadge(thinking, data);
    renderPlan(thinking, data.plan);
    renderTimetable(thinking, data.plan);
    renderFeedback(thinking, data.plan, data.explanation);
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
