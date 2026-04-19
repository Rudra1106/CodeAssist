import os
import json
from datetime import datetime
from typing import Optional
from pymongo import MongoClient, DESCENDING
from pymongo.collection import Collection
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DB_NAME   = "atlas_dev"

# ── Connection ─────────────────────────────────────────────────────────────────

_client: Optional[MongoClient] = None

def get_db():
    global _client
    if _client is None:
        _client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
    return _client[DB_NAME]


def init_db():
    """
    Create indexes on first run.
    Safe to call every startup — MongoDB ignores duplicate index creation.
    """
    db = get_db()

    db.sessions.create_index([("created_at", DESCENDING)])
    db.messages.create_index([("session_id", 1), ("created_at", 1)])
    db.project_context.create_index([("working_dir", 1), ("key", 1)], unique=True)
    db.user_patterns.create_index([("pattern", 1)], unique=True)
    db.execution_history.create_index([("file_path", 1), ("created_at", DESCENDING)])

    print(f"[Memory] MongoDB connected → {DB_NAME}")


# ── Sessions ───────────────────────────────────────────────────────────────────

def save_session(session_id: str, goal: str, mode: str):
    db = get_db()
    db.sessions.update_one(
        {"_id": session_id},
        {"$setOnInsert": {
            "_id":        session_id,
            "created_at": datetime.now().isoformat(),
            "goal":       goal,
            "mode":       mode,
            "status":     "running",
            "retries":    0,
            "files":      []
        }},
        upsert=True
    )


def update_session(session_id: str, status: str, retries: int, files: list[str]):
    db = get_db()
    db.sessions.update_one(
        {"_id": session_id},
        {"$set": {
            "status":     status,
            "retries":    retries,
            "files":      files,
            "updated_at": datetime.now().isoformat()
        }}
    )


def get_recent_sessions(limit: int = 5) -> list[dict]:
    db = get_db()
    docs = db.sessions.find(
        {},
        {"_id": 1, "created_at": 1, "goal": 1, "status": 1, "files": 1}
    ).sort("created_at", DESCENDING).limit(limit)
    return list(docs)


# ── Messages ───────────────────────────────────────────────────────────────────

def save_message(session_id: str, agent: str, role: str, content: str):
    db = get_db()
    db.messages.insert_one({
        "session_id": session_id,
        "agent":      agent,
        "role":       role,
        "content":    content,
        "created_at": datetime.now().isoformat()
    })


# ── Project context ────────────────────────────────────────────────────────────

def set_project_context(working_dir: str, key: str, value: str):
    """Upsert a key-value fact about a project directory."""
    db = get_db()
    db.project_context.update_one(
        {"working_dir": working_dir, "key": key},
        {"$set": {
            "value":      value,
            "updated_at": datetime.now().isoformat()
        }},
        upsert=True
    )


def get_project_context(working_dir: str) -> dict:
    db = get_db()
    docs = db.project_context.find({"working_dir": working_dir})
    return {d["key"]: d["value"] for d in docs}


# ── User patterns ──────────────────────────────────────────────────────────────

def record_pattern(pattern: str, category: str):
    """
    Increment count if pattern exists, insert fresh if not.
    Categories: 'mistake' | 'preference' | 'skill' | 'habit'
    """
    db = get_db()
    db.user_patterns.update_one(
        {"pattern": pattern},
        {
            "$inc":      {"count": 1},
            "$set":      {"last_seen": datetime.now().isoformat()},
            "$setOnInsert": {
                "category":   category,
                "created_at": datetime.now().isoformat()
            }
        },
        upsert=True
    )


def get_user_patterns(category: Optional[str] = None, limit: int = 10) -> list[dict]:
    db = get_db()
    query = {"category": category} if category else {}
    docs  = db.user_patterns.find(query).sort("count", DESCENDING).limit(limit)
    return list(docs)


# ── Execution history ──────────────────────────────────────────────────────────

def save_execution(session_id: str, file_path: str, success: bool,
                   error: str = "", output: str = ""):
    db = get_db()
    db.execution_history.insert_one({
        "session_id": session_id,
        "file_path":  file_path,
        "success":    success,
        "error":      error,
        "output":     output,
        "created_at": datetime.now().isoformat()
    })


def get_execution_history(file_path: str, limit: int = 5) -> list[dict]:
    db = get_db()
    docs = db.execution_history.find(
        {"file_path": file_path}
    ).sort("created_at", DESCENDING).limit(limit)
    return list(docs)


# ── Memory summary for agents ──────────────────────────────────────────────────

def build_memory_context(working_dir: str) -> str:
    """
    Compact memory string injected into every agent's system prompt.
    Agents use this to understand project history and user patterns.
    """
    lines = []

    # Recent sessions
    sessions = get_recent_sessions(limit=3)
    if sessions:
        lines.append("=== Recent sessions ===")
        for s in sessions:
            files = s.get("files", [])
            lines.append(
                f"- [{s['created_at'][:10]}] {s['goal'][:60]}"
                f" → {s['status']} | files: {files}"
            )

    # Project context
    ctx = get_project_context(working_dir)
    if ctx:
        lines.append("\n=== Project context ===")
        for k, v in ctx.items():
            lines.append(f"- {k}: {v}")

    # User patterns — mistakes and skills only (most useful for agents)
    patterns = get_user_patterns(limit=6)
    if patterns:
        lines.append("\n=== User patterns ===")
        for p in patterns:
            lines.append(
                f"- [{p['category']}] {p['pattern']} (seen {p['count']}x)"
            )

    return "\n".join(lines) if lines else "No prior memory for this project."