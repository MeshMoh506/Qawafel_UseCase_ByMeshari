"""API for the reviewer screens. The routes follow the read side of the spec in section 2.2:
GET  /v1/package-versions/{id}/summary
GET  /v1/package-versions/{id}/figures/{key}
GET  /v1/package-versions/{id}/flags
POST /v1/flags/{id}/resolve          (note required)
The prototype holds one package, called "demo". Flag resolutions are kept in memory and reset on restart.
"""
import hashlib
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .analysis import INV_FILE, STMT_FILE, Analysis
from .evaluate import evaluate
from .views import figure, flag_json, summary

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("DATA_DIR", ROOT / "data" / "sample"))
STATIC_DIR = Path(os.environ.get("STATIC_DIR", ROOT / "frontend" / "dist"))
STATE: dict = {}


def load() -> Analysis:
    return Analysis(str(DATA_DIR / INV_FILE), str(DATA_DIR / STMT_FILE))


@asynccontextmanager
async def lifespan(app: FastAPI):
    a = load()
    h = hashlib.sha256()
    for name in (INV_FILE, STMT_FILE):
        h.update((DATA_DIR / name).read_bytes())
    STATE["analysis"] = a
    STATE["hash"] = h.hexdigest()
    STATE["eval"] = evaluate(a, str(DATA_DIR))
    yield


app = FastAPI(title="Financing package prototype", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], allow_methods=["*"], allow_headers=["*"])


def A() -> Analysis:
    return STATE["analysis"]


def check_id(pid: str):
    if pid != "demo":
        raise HTTPException(404, "Unknown package version. This prototype holds one package, called 'demo'.")


@app.get("/api/health")
def health():
    return {"ok": True, "invoices": len(A().invoices), "bank_lines": len(A().txns)}


@app.get("/v1/package-versions/{pid}/summary")
def get_summary(pid: str):
    check_id(pid)
    s = summary(A())
    s["version"] = {"id": "demo", "version_no": 1, "content_hash": STATE["hash"]}
    return s


@app.get("/v1/package-versions/{pid}/figures/{key:path}")
def get_figure(pid: str, key: str):
    check_id(pid)
    f = figure(A(), key)
    if f is None:
        raise HTTPException(404, f"No figure called '{key}'.")
    return f


@app.get("/v1/package-versions/{pid}/flags")
def get_flags(pid: str):
    check_id(pid)
    return [flag_json(f) for f in A().flags]


class Resolve(BaseModel):
    note: str
    by: str = "Analyst"


@app.post("/v1/flags/{flag_id}/resolve")
def resolve_flag(flag_id: str, body: Resolve):
    try:
        f = A().resolve(flag_id, body.note, body.by)
    except KeyError:
        raise HTTPException(404, "No such flag.")
    except ValueError as e:
        raise HTTPException(409, {"error": {"code": "note_required", "message": str(e)}})
    return flag_json(f)


@app.post("/v1/flags/{flag_id}/reopen")
def reopen_flag(flag_id: str):
    f = A().flag_by_id.get(flag_id)
    if not f:
        raise HTTPException(404, "No such flag.")
    f.resolved = None
    return flag_json(f)


@app.get("/v1/package-versions/{pid}/method")
def get_method(pid: str):
    check_id(pid)
    return {"evaluation": STATE["eval"]}


if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        f = STATIC_DIR / path
        return FileResponse(f if path and f.is_file() else STATIC_DIR / "index.html")
