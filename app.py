from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib import error, request
from urllib.parse import urlparse

DATA_PATH = Path("data/comments_store.json")
HOST = "0.0.0.0"
PORT = 8501
OPENAI_URL = "https://api.openai.com/v1/chat/completions"
OPENAI_MODEL = "gpt-4o-mini"


@dataclass
class Comment:
    id: int
    text: str
    created_at: str


@dataclass
class ConsolidatedComment:
    comment_id: int
    consolidated_text: str
    created_at: str


def utc_now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds")


def empty_store() -> dict:
    return {"comments": [], "consolidated_comments": [], "executive_summaries": []}


def ensure_store() -> None:
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not DATA_PATH.exists():
        DATA_PATH.write_text(json.dumps(empty_store(), indent=2), encoding="utf-8")


def load_store() -> dict:
    ensure_store()
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


def save_store(store: dict) -> None:
    DATA_PATH.write_text(json.dumps(store, indent=2, ensure_ascii=False), encoding="utf-8")


def reset_store() -> None:
    save_store(empty_store())


def call_openai(api_key: str, system_prompt: str, user_prompt: str) -> str:
    payload = {
        "model": OPENAI_MODEL,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    req = request.Request(
        OPENAI_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=45) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"OpenAI HTTPError {exc.code}: {detail}") from exc
    except Exception as exc:
        raise RuntimeError(f"OpenAI request failed: {exc}") from exc

    try:
        return data["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        raise RuntimeError(f"Unexpected OpenAI response: {data}") from exc


def improve_comment_with_openai(api_key: str, comment_text: str, improvement_rules: str) -> dict:
    system_prompt = (
        "You are an expert financial reporting coach. "
        "Evaluate comment quality against the provided rules and return strict JSON."
    )
    user_prompt = f"""
Rules for quality/completeness:
{improvement_rules}

Controller comment:
{comment_text}

Return ONLY valid JSON with this exact schema:
{{
  "quality_assessment": "short assessment",
  "suggestions": ["suggestion 1", "suggestion 2", "suggestion 3"],
  "revised_comment": "improved version; if missing info use placeholders like <ADD_DRIVER>",
  "missing_information": ["missing item 1", "missing item 2"]
}}
""".strip()
    raw = call_openai(api_key, system_prompt, user_prompt)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {
            "quality_assessment": "Model output was not strict JSON. Showing raw output.",
            "suggestions": ["Retry with clearer rules in configuration panel."],
            "revised_comment": raw,
            "missing_information": [],
        }


def translate_to_english_with_openai(api_key: str, text: str) -> str:
    system_prompt = "Translate user comments into clear, professional English. Output only translated text."
    user_prompt = f"Translate to English:\n{text}"
    return call_openai(api_key, system_prompt, user_prompt)


def consolidate_comment_with_openai(api_key: str, text: str, tone_rules: str) -> str:
    system_prompt = "You standardize controller comments for consistency, readability, and professional tone."
    user_prompt = f"""
Tone/style rules:
{tone_rules}

Comment to consolidate:
{text}

Return only the final consolidated comment.
""".strip()
    return call_openai(api_key, system_prompt, user_prompt)


def update_executive_summary_with_openai(store: dict, api_key: str) -> None:
    comments = store.get("consolidated_comments", [])
    if not comments:
        summary_text = "No consolidated comments available yet."
    else:
        context = "\n".join(f"- {row['consolidated_text']}" for row in comments)
        system_prompt = "You write executive summaries for management reporting."
        user_prompt = (
            "Create one concise executive summary in English based on all consolidated comments below.\n"
            "Focus on themes, key risks/opportunities, and suggested direction.\n\n"
            f"Consolidated comments:\n{context}"
        )
        summary_text = call_openai(api_key, system_prompt, user_prompt)

    store["executive_summaries"] = [{"summary_text": summary_text, "created_at": utc_now()}]


def answer_question_with_openai(api_key: str, question: str, consolidated_comments: list[dict]) -> str:
    if not consolidated_comments:
        return "No consolidated comments available for analysis yet."

    context = "\n".join(f"- {row['consolidated_text']}" for row in consolidated_comments)
    system_prompt = "You are an analytical assistant. Answer with evidence from provided consolidated comments only."
    user_prompt = (
        f"Question:\n{question}\n\n"
        "Consolidated comments context:\n"
        f"{context}\n\n"
        "Provide a concise analysis in English."
    )
    return call_openai(api_key, system_prompt, user_prompt)


INDEX_HTML = """
<!doctype html>
<html>
<head>
  <meta charset='utf-8'/>
  <meta name='viewport' content='width=device-width, initial-scale=1'/>
  <title>AI Comments Workbench</title>
  <style>
    body { font-family: Arial, sans-serif; background:#0f172a; color:#e2e8f0; margin:0; }
    .container { max-width:1150px; margin:20px auto; padding:0 16px; }
    .card { background:#1e293b; border-radius:10px; padding:16px; margin-bottom:14px; }
    textarea,input,button { width:100%; padding:10px; margin-top:8px; border-radius:8px; border:1px solid #334155; background:#0b1220; color:#e2e8f0; box-sizing:border-box; }
    .checkbox-line { display:flex; align-items:center; gap:8px; margin-top:8px; }
    .checkbox-line input[type='checkbox'] { width:auto; margin:0; padding:0; }
    button { background:#22c55e; color:#052e16; font-weight:700; cursor:pointer; }
    table { width:100%; border-collapse:collapse; margin-top:8px; }
    th,td { border:1px solid #334155; padding:8px; text-align:left; font-size:14px; vertical-align:top; }
    .row { display:grid; grid-template-columns:2fr 1fr; gap:12px; }
    .hint { color:#93c5fd; font-size:14px; }
    .topbar { display:flex; justify-content:space-between; align-items:center; margin-bottom:12px; gap:12px; }
    .top-actions { display:flex; gap:8px; }
    .gear { width:auto; padding:8px 12px; background:#94a3b8; color:#0f172a; }
    .danger { width:auto; padding:8px 12px; background:#ef4444; color:#fff; }
    .modal-backdrop { display:none; position:fixed; inset:0; background:rgba(15,23,42,0.7); z-index:1000; }
    .modal { max-width:820px; margin:6vh auto; background:#1e293b; border-radius:10px; padding:16px; border:1px solid #334155; }
    .modal-actions { display:flex; gap:8px; margin-top:8px; }
    .secondary { background:#64748b; color:#f8fafc; }
    .warn { color:#fca5a5; }
    #summaryText { white-space: normal; line-height:1.5; }
  </style>
</head>
<body>
<div class='container'>
  <div class='topbar'>
    <div>
      <h1>AI Comments Workbench</h1>
      <p>Prototype: comment workflow, consolidation, auto-summary, and AI analysis.</p>
    </div>
    <div class='top-actions'>
      <button class='danger' onclick='resetAllData()'>🗑️ Reset all data</button>
      <button class='gear' onclick='openConfig()'>⚙️ Configuration</button>
    </div>
  </div>


  <div class='card'>
    <h3>1) Financial performance snapshot (example data)</h3>
    <p class='hint'>Hypothetical company KPI view for comparative commentary (2025 vs 2024, multi-country).</p>

    <table>
      <tr>
        <th>Country</th>
        <th>Revenue 2024 (M€)</th>
        <th>Revenue 2025 (M€)</th>
        <th>EBITDA Margin 2024</th>
        <th>EBITDA Margin 2025</th>
        <th>Operating Cash Flow 2024 (M€)</th>
        <th>Operating Cash Flow 2025 (M€)</th>
      </tr>
      <tr><td>Italy</td><td>420</td><td>390</td><td>18.2%</td><td>15.1%</td><td>61</td><td>47</td></tr>
      <tr><td>Germany</td><td>310</td><td>430</td><td>14.7%</td><td>20.4%</td><td>38</td><td>72</td></tr>
      <tr><td>Spain</td><td>190</td><td>230</td><td>12.9%</td><td>14.2%</td><td>25</td><td>33</td></tr>
      <tr><td>France</td><td>280</td><td>275</td><td>16.1%</td><td>15.4%</td><td>44</td><td>40</td></tr>
    </table>

    <table>
      <tr>
        <th>Group KPI</th>
        <th>2024</th>
        <th>2025</th>
        <th>Comment cue</th>
      </tr>
      <tr><td>Total Revenue (M€)</td><td>1,200</td><td>1,325</td><td>Group growth driven mostly by Germany and Spain.</td></tr>
      <tr><td>Weighted EBITDA Margin</td><td>15.8%</td><td>17.0%</td><td>Profitability improved despite Italy decline.</td></tr>
      <tr><td>Total Operating Cash Flow (M€)</td><td>168</td><td>192</td><td>Cash conversion strengthened in core growth markets.</td></tr>
    </table>

    <p class='hint'>Storyline: Italy contracted in volume and margin (pricing pressure), while Germany had strong recovery and mix improvement. Spain accelerated from new client wins; France stayed broadly stable. Net effect: company-level performance improved even with one country underperforming.</p>
  </div>

  <div class='card'>
    <h3>2) Insert comment</h3>
    <div class='row'>
      <div>
        <label>Comment</label>
        <textarea id='commentText' rows='7' placeholder='Write your comment...'></textarea>
      </div>
      <div>
        <label class='checkbox-line'><input type='checkbox' id='guidance'/> <span>Suggest improvements before submit</span></label>
        <label class='checkbox-line'><input type='checkbox' id='translate'/> <span>Normalize to English before submit</span></label>
        <button onclick='saveComment()'>Save comment</button>
        <p class='hint'>If improvement is enabled, the first click opens a popup with suggestions and revised text. Then edit/copy and save again.</p>
      </div>
    </div>
    <div id='saveMessage' class='hint'></div>
  </div>

  <div class='card'><h3>3) Raw comments</h3><div id='commentsTable'></div></div>
  <div class='card'><h3>4) AI consolidated comments</h3><div id='consolidatedTable'></div></div>
  <div class='card'>
    <h3>5) Executive summary</h3>
    <div id='summaryText' class='hint'></div>
    <p id='summaryMeta' class='hint'></p>
  </div>

  <div class='card'>
    <h3>6) Analysis Q&A</h3>
    <input id='question' placeholder='Ask a question about consolidated comments' />
    <button onclick='askQuestion()'>Analyze</button>
    <p id='answer'></p>
  </div>
</div>

<div id='configBackdrop' class='modal-backdrop'>
  <div class='modal'>
    <h3>Configuration panel</h3>
    <label>OpenAI API Key</label>
    <input id='apiKey' type='password' placeholder='sk-...' />
    <label>Tone of voice rules (free text)</label>
    <textarea id='toneRules' rows='5' placeholder='Example: Use concise executive tone, avoid jargon, prioritize actionability.'></textarea>
    <label>Improvements rules (free text)</label>
    <textarea id='improvementRules' rows='5' placeholder='Example: Comment must include context, cause, quantified impact, and next action owner.'></textarea>
    <div class='modal-actions'>
      <button onclick='saveConfig()'>Save configuration</button>
      <button class='secondary' onclick='closeConfig()'>Close</button>
    </div>
    <p class='hint'>Config is stored only in browser localStorage and sent with requests.</p>
  </div>
</div>

<div id='improveBackdrop' class='modal-backdrop'>
  <div class='modal'>
    <h3>Suggested improvements</h3>
    <p><strong>Quality assessment</strong></p>
    <p id='qualityAssessment' class='hint'></p>
    <p><strong>Suggestions</strong></p>
    <ul id='suggestionsList'></ul>
    <p><strong>Missing information</strong></p>
    <ul id='missingInfoList'></ul>
    <p><strong>Revised comment (copy/edit before final save)</strong></p>
    <textarea id='revisedComment' rows='6'></textarea>
    <div class='modal-actions'>
      <button onclick='useRevisedComment()'>Use revised text in input</button>
      <button class='secondary' onclick='closeImprove()'>Close</button>
    </div>
  </div>
</div>

<script>
let improvementReady = false;

function getConfig() {
  return {
    apiKey: localStorage.getItem('apiKey') || '',
    toneRules: localStorage.getItem('toneRules') || '',
    improvementRules: localStorage.getItem('improvementRules') || '',
  };
}

function fillConfig() {
  const c = getConfig();
  document.getElementById('apiKey').value = c.apiKey;
  document.getElementById('toneRules').value = c.toneRules;
  document.getElementById('improvementRules').value = c.improvementRules;
}

function saveConfig() {
  localStorage.setItem('apiKey', document.getElementById('apiKey').value.trim());
  localStorage.setItem('toneRules', document.getElementById('toneRules').value.trim());
  localStorage.setItem('improvementRules', document.getElementById('improvementRules').value.trim());
  closeConfig();
}

function openConfig() { fillConfig(); document.getElementById('configBackdrop').style.display = 'block'; }
function closeConfig() { document.getElementById('configBackdrop').style.display = 'none'; }
function openImprove() { document.getElementById('improveBackdrop').style.display = 'block'; }
function closeImprove() { document.getElementById('improveBackdrop').style.display = 'none'; }

function listHtml(id, items) {
  const el = document.getElementById(id);
  el.innerHTML = '';
  (items || []).forEach(i => {
    const li = document.createElement('li');
    li.innerText = i;
    el.appendChild(li);
  });
}

async function api(path, method='GET', body=null) {
  const res = await fetch(path, {method, headers:{'Content-Type':'application/json'}, body: body?JSON.stringify(body):null});
  return res.json();
}

function tableFromRows(rows) {
  if (!rows || !rows.length) return '<p class="hint">No data yet.</p>';
  const headers = Object.keys(rows[0]);
  const thead = '<tr>'+headers.map(h=>`<th>${h}</th>`).join('')+'</tr>';
  const body = rows.map(r=>'<tr>'+headers.map(h=>`<td>${r[h] ?? ''}</td>`).join('')+'</tr>').join('');
  return `<table>${thead}${body}</table>`;
}

function escapeHtml(text) {
  return (text || '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;');
}

function renderMarkdownSimple(text) {
  let html = escapeHtml(text || 'No executive summary generated yet.');
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
  html = html.replace(/`(.+?)`/g, '<code>$1</code>');
  html = html.split(String.fromCharCode(10)).join('<br>');
  return html;
}

async function refresh() {
  const state = await api('/api/state');
  document.getElementById('commentsTable').innerHTML = tableFromRows(state.comments);
  document.getElementById('consolidatedTable').innerHTML = tableFromRows(state.consolidated_comments);

  const latestSummary = (state.executive_summaries && state.executive_summaries.length)
    ? state.executive_summaries[state.executive_summaries.length - 1]
    : null;

  document.getElementById('summaryText').innerHTML = renderMarkdownSimple(latestSummary ? latestSummary.summary_text : 'No executive summary generated yet.');
  document.getElementById('summaryMeta').innerText = latestSummary ? `Updated at: ${latestSummary.created_at}` : '';
}

async function resetAllData() {
  const ok = window.confirm('Delete all comments, consolidated comments and summary?');
  if (!ok) return;
  const res = await api('/api/reset', 'POST', {});
  const msg = document.getElementById('saveMessage');
  if (res.error) {
    msg.innerHTML = `<span class='warn'>${res.error}</span>`;
    return;
  }
  msg.innerText = 'All data cleared.';
  improvementReady = false;
  document.getElementById('commentText').value = '';
  document.getElementById('answer').innerText = '';
  refresh();
}

async function saveComment() {
  const cfg = getConfig();
  const payload = {
    text: document.getElementById('commentText').value,
    suggest_improvements: document.getElementById('guidance').checked,
    normalize_english: document.getElementById('translate').checked,
    reviewed: improvementReady,
    api_key: cfg.apiKey,
    tone_rules: cfg.toneRules,
    improvement_rules: cfg.improvementRules,
  };

  const res = await api('/api/comment', 'POST', payload);
  const msg = document.getElementById('saveMessage');

  if (res.error) {
    msg.innerHTML = `<span class='warn'>${res.error}</span>`;
    return;
  }

  if (res.requires_review) {
    document.getElementById('qualityAssessment').innerText = res.quality_assessment || '';
    listHtml('suggestionsList', res.suggestions || []);
    listHtml('missingInfoList', res.missing_information || []);
    document.getElementById('revisedComment').value = res.revised_comment || '';
    openImprove();
    improvementReady = true;
    msg.innerText = 'Improvements generated. Review/edit the revised comment and then save again.';
    return;
  }

  msg.innerText = 'Comment saved successfully. Consolidated table and executive summary were auto-updated.';
  improvementReady = false;
  document.getElementById('commentText').value = '';
  refresh();
}

function useRevisedComment() {
  document.getElementById('commentText').value = document.getElementById('revisedComment').value;
  closeImprove();
}

async function askQuestion() {
  const cfg = getConfig();
  const q = document.getElementById('question').value;
  const res = await api('/api/ask', 'POST', { question: q, api_key: cfg.apiKey });
  document.getElementById('answer').innerText = res.answer || res.error || 'No answer.';
}

document.getElementById('commentText').addEventListener('input', () => { improvementReady = false; });
refresh();
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, payload: dict, status: int = HTTPStatus.OK) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _read_json(self) -> dict:
        size = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(size).decode("utf-8") if size else "{}"
        return json.loads(raw or "{}")

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/":
            body = INDEX_HTML.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/api/state":
            store = load_store()
            self._send_json(
                {
                    "comments": store["comments"],
                    "consolidated_comments": store["consolidated_comments"],
                    "executive_summaries": store["executive_summaries"],
                }
            )
            return

        self._send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        if self.path == "/api/reset":
            reset_store()
            self._send_json({"status": "ok"})
            return

        if self.path == "/api/comment":
            body = self._read_json()
            text = (body.get("text") or "").strip()
            api_key = (body.get("api_key") or "").strip()
            suggest_improvements = bool(body.get("suggest_improvements", False))
            normalize_english = bool(body.get("normalize_english", False))
            reviewed = bool(body.get("reviewed", False))
            tone_rules = (body.get("tone_rules") or "").strip()
            improvement_rules = (body.get("improvement_rules") or "").strip()

            if not text:
                self._send_json({"error": "Comment text is required."}, status=HTTPStatus.BAD_REQUEST)
                return
            if not api_key:
                self._send_json({"error": "OpenAI API key is required in configuration."}, status=HTTPStatus.BAD_REQUEST)
                return

            if suggest_improvements and not reviewed:
                if not improvement_rules:
                    self._send_json(
                        {"error": "Please set 'Improvements rules' in configuration before requesting suggestions."},
                        status=HTTPStatus.BAD_REQUEST,
                    )
                    return
                try:
                    result = improve_comment_with_openai(api_key, text, improvement_rules)
                except RuntimeError as exc:
                    self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_GATEWAY)
                    return
                self._send_json({"requires_review": True, **result})
                return

            final_text = text
            try:
                if normalize_english:
                    final_text = translate_to_english_with_openai(api_key, final_text)

                consolidated = consolidate_comment_with_openai(
                    api_key,
                    final_text,
                    tone_rules or "Use professional and consistent tone with strong readability.",
                )
            except RuntimeError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_GATEWAY)
                return

            store = load_store()
            comment_id = len(store["comments"]) + 1

            comment = Comment(id=comment_id, text=final_text, created_at=utc_now())
            store["comments"].append(asdict(comment))

            consolidated_row = ConsolidatedComment(
                comment_id=comment_id,
                consolidated_text=consolidated,
                created_at=utc_now(),
            )
            store["consolidated_comments"].append(asdict(consolidated_row))

            try:
                update_executive_summary_with_openai(store, api_key)
            except RuntimeError as exc:
                self._send_json({"error": f"Comment saved, but summary update failed: {exc}"}, status=HTTPStatus.BAD_GATEWAY)
                return

            save_store(store)
            self._send_json({"status": "ok"})
            return

        if self.path == "/api/ask":
            body = self._read_json()
            question = (body.get("question") or "").strip()
            api_key = (body.get("api_key") or "").strip()
            if not question:
                self._send_json({"answer": "Please insert a question."})
                return
            if not api_key:
                self._send_json({"error": "OpenAI API key is required in configuration."}, status=HTTPStatus.BAD_REQUEST)
                return
            store = load_store()
            try:
                answer = answer_question_with_openai(api_key, question, store["consolidated_comments"])
            except RuntimeError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_GATEWAY)
                return
            self._send_json({"answer": answer})
            return

        self._send_json({"error": "Not found"}, status=HTTPStatus.NOT_FOUND)


def run() -> None:
    ensure_store()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Serving on http://{HOST}:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    run()
