import os
import uuid
import psycopg2
from fastapi import FastAPI, Body
from pydantic import BaseModel

DATABASE_URL = os.environ.get("DATABASE_URL", "postgres://app_user:app_pass@db:5432/app_db")

app = FastAPI(title="LLM Memory API")

def get_conn():
    return psycopg2.connect(DATABASE_URL)

class ChatEvent(BaseModel):
    session_id: str
    role: str  # 'user' | 'assistant' | 'system'
    content: str

@app.post("/chat")
def add_chat_event(event: ChatEvent):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO app.chat_events (session_id, role, content)
        VALUES (%s, %s, %s)
        RETURNING event_id, created_at
        """,
        (event.session_id, event.role, event.content),
    )
    row = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    return {"event_id": row[0], "created_at": row[1]}

@app.get("/memories")
def list_memories(limit: int = 10):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT memory_id, session_id, kind, text, importance, created_at
        FROM app.memories
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (limit,),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [
        {
            "memory_id": r[0],
            "session_id": r[1],
            "kind": r[2],
            "text": r[3],
            "importance": float(r[4]),
            "created_at": r[5],
        }
        for r in rows
    ]
