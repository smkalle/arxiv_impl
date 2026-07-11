"""Minimal FastAPI dashboard for human validation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse

from src.evolution import load_state
from src.index import load_jsonl
from src.retrieve import evolved_retrieve, load_index


app = FastAPI(title="TicketMind Dashboard")


def page(title: str, body: str) -> HTMLResponse:
    return HTMLResponse(
        f"""<!doctype html>
<html><head><title>{title}</title><style>
body{{font-family:Arial,sans-serif;margin:24px;line-height:1.4}}
table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #ddd;padding:6px}}
textarea{{width:100%;height:90px}}pre{{background:#f5f5f5;padding:12px;overflow:auto}}
.ok{{color:#136f2d}}.warn{{color:#9a6700}}
</style></head><body>
<nav><a href="/">Query Inspector</a> | <a href="/kb">KB</a> | <a href="/evolution">Evolution</a> | <a href="/system">System</a></nav>
{body}</body></html>"""
    )


@app.get("/", response_class=HTMLResponse)
def home() -> HTMLResponse:
    return page(
        "TicketMind Query Inspector",
        """<h1>TicketMind Query Inspector</h1>
<form method="post" action="/query/trace">
<textarea name="ticket">app keeps crashing on login</textarea>
<p><button type="submit">Run Query</button></p>
</form>""",
    )


@app.post("/query/trace", response_class=HTMLResponse)
def query_trace(ticket: str = Form(...)) -> HTMLResponse:
    load_index("data/bm25_index.pkl")
    payload = evolved_retrieve(ticket)
    rows = "".join(
        f"<tr><td>{r['rank']}</td><td>{r['id']}</td><td>{r['title']}</td><td>{r['score']:.3f}</td></tr>"
        for r in payload["results"]
    )
    body = f"""<h1>Query Inspector</h1><p><strong>Ticket:</strong> {ticket}</p>
<h2>Results</h2><table><tr><th>Rank</th><th>ID</th><th>Title</th><th>Score</th></tr>{rows}</table>
<h2>Trace</h2><pre>{json.dumps(payload['trace'], indent=2)}</pre>"""
    return page("Query Trace", body)


@app.get("/kb", response_class=HTMLResponse)
def kb() -> HTMLResponse:
    path = Path("data/enriched_corpus.jsonl")
    articles = load_jsonl(path if path.exists() else "data/kb_corpus.jsonl")
    rows = "".join(
        f"<tr><td>{a['id']}</td><td>{a['title']}</td><td>{len(a.get('enriched_terms', []))}</td></tr>"
        for a in articles
    )
    return page("KB", f"<h1>KB Browser</h1><table><tr><th>ID</th><th>Title</th><th>Enriched Terms</th></tr>{rows}</table>")


@app.get("/evolution", response_class=HTMLResponse)
def evolution() -> HTMLResponse:
    state = load_state()
    rows = "".join(
        f"<tr><td>{r['round']}</td><td>{r['f1_at_5']}</td><td>{r['strategy']}</td><td>{r['validation']}</td></tr>"
        for r in state["history"]
    )
    return page("Evolution", f"<h1>Evolution Monitor</h1><p>Mode: {state['mode']}</p><table><tr><th>Round</th><th>F1</th><th>Strategy</th><th>Validation</th></tr>{rows}</table>")


@app.get("/system", response_class=HTMLResponse)
def system() -> HTMLResponse:
    state = load_state()
    index = Path("data/bm25_index.pkl")
    corpus = Path("data/enriched_corpus.jsonl")
    body = f"""<h1>System Health</h1>
<p class="{'ok' if index.exists() else 'warn'}">Index: {index.exists()}</p>
<p class="{'ok' if corpus.exists() else 'warn'}">Enriched corpus: {corpus.exists()}</p>
<pre>{json.dumps(state['dependencies'], indent=2)}</pre>"""
    return page("System", body)
