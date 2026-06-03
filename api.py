"""
api.py — the HTTP layer between the React frontend and the agent.

Run locally:
    uvicorn api:app --reload --port 8000

Then open http://127.0.0.1:8000/docs — FastAPI's interactive docs let you
POST questions straight from the browser, before any frontend exists.

Endpoints:
    GET  /api/health   -> {"ok": true, "data": "sample_data"}
    POST /api/ask      -> {"answer", "sql": [...], "results": [...]}

If a built React app exists at ui/dist, it's served at / — so one process
serves both API and UI (one service, one deploy, one link).
"""

import os
import threading

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from landed import llm
from landed.agent import ask as agent_ask
from landed.db import build

load_dotenv()

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = (os.path.join(HERE, "real_data")
            if os.path.isdir(os.path.join(HERE, "real_data"))
            else os.path.join(HERE, "sample_data"))

app = FastAPI(title="Landed", version="0.1",
              description="Ask your job-search pipeline anything.")

# Dev convenience: the Vite dev server (localhost:5173) calls this API
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])

con = build(DATA_DIR)
client = llm.from_env()
_lock = threading.Lock()  # one DuckDB connection; serialise agent runs


class Question(BaseModel):
    question: str


@app.get("/api/health")
def health():
    return {"ok": True, "data": os.path.basename(DATA_DIR)}


@app.post("/api/ask")
def ask(q: Question):
    question = q.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Empty question.")
    with _lock:
        return agent_ask(question, con, client)


# Serve the built React app (ui/dist) at / when it exists
_ui_dist = os.path.join(HERE, "ui", "dist")
if os.path.isdir(_ui_dist):
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory=_ui_dist, html=True), name="ui")
