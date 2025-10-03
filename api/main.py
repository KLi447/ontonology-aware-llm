import os
import psycopg2
import json
from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from google import genai

GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
client = None
if GOOGLE_API_KEY:
    try:
        client = genai.Client(api_key=GOOGLE_API_KEY)
        print("Google Gemini client configured.")
    except Exception as e:
        print(f"Could not configure Gemini client: {e}")
else:
    print("GOOGLE_API_KEY not set!")

DATABASE_URL = os.environ.get("DATABASE_URL", "postgres://app_user:app_pass@db:5432/app_db")

def convert_to_gemini_contents(history, system_instruction: str, user_prompt: str):
    contents = []

    if system_instruction:
        contents.append({
            "role": "user",
            "parts": [{"text": system_instruction}]
        })

    for role, content in history:
        if role == "assistant":
            contents.append({
                "role": "model",
                "parts": [{"text": content}]
            })
        else:  # role == "user"
            contents.append({
                "role": "user",
                "parts": [{"text": content}]
            })

    # Current user prompt
    contents.append({
        "role": "user",
        "parts": [{"text": user_prompt}]
    })

    return contents


def get_conn():
    return psycopg2.connect(DATABASE_URL)

def add_chat_event_db(session_id: str, role: str, content: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO app.chat_events (session_id, role, content) VALUES (%s, %s, %s)",
        (session_id, role, content),
    )
    conn.commit()
    cur.close()
    conn.close()

def create_memory_db(session_id: str, text: str, importance: float = 0.5):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO app.memories (session_id, kind, text, importance) VALUES (%s, %s, %s, %s)",
        (session_id, 'reflection', text, importance),
    )
    conn.commit()
    cur.close()
    conn.close()
    print(f"Memory created for session {session_id}: {text}")

app = FastAPI(title="LLM Memory API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory="static"), name="static")

class ChatEvent(BaseModel):
    session_id: str
    role: str
    content: str

class GenerateRequest(BaseModel):
    session_id: str
    prompt: str

@app.get("/", response_class=FileResponse)
async def read_root():
    return "static/index.html"

async def create_memory_from_conversation(session_id: str, user_prompt: str, assistant_response: str):
    if not client:
        return
    try:
        conversation_summary = f"User asked: '{user_prompt}'. Assistant responded: '{assistant_response}'."
        prompt = f"You are a memory creation agent. Based on the following conversation turn, extract the single most important, concise fact to remember for future conversations. Respond with 'NULL' if nothing is important.\n\nConversation:\n{conversation_summary}"
        
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )
        memory_text = response.text.strip()

        if memory_text and memory_text.upper() != "NULL":
            create_memory_db(session_id, memory_text)
    except Exception as e:
        print(f"Error creating memory with Gemini: {e}")

@app.post("/generate")
async def generate_response(req: GenerateRequest):
    if not client:
        async def error_stream():
            yield "data: {\"error\": \"Gemini client not configured.\"}\n\n"
        return StreamingResponse(error_stream(), media_type="text/event-stream")

    add_chat_event_db(req.session_id, 'user', req.prompt)

    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT role, content FROM app.chat_events WHERE session_id = %s ORDER BY created_at DESC LIMIT 10",
        (req.session_id,),
    )
    history = cur.fetchall()[::-1]
    cur.execute(
        "SELECT text FROM app.memories WHERE session_id = %s ORDER BY created_at DESC LIMIT 5",
        (req.session_id,),
    )
    memories = cur.fetchall()
    cur.close()
    conn.close()

    memory_str = "Key memories for this user:\n" + "\n".join([f"- {m[0]}" for m in memories]) if memories else "No prior memories."
    system_instruction = f"You are a helpful assistant. Here is context about the user:\n{memory_str}"

    contents = convert_to_gemini_contents(history, system_instruction, req.prompt)

    async def response_streamer():
        try:
            stream = client.models.generate_content_stream(
                model="gemini-2.5-flash",
                contents=contents,
            )

            full_response = ""
            for event in stream:
                if event.text:
                    full_response += event.text
                    yield f"data: {json.dumps({'token': event.text})}\n\n"

            add_chat_event_db(req.session_id, 'assistant', full_response)
            await create_memory_from_conversation(req.session_id, req.prompt, full_response)

            yield f"data: {json.dumps({'status': 'done'})}\n\n"

        except Exception as e:
            print(f"Error during Gemini stream: {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(response_streamer(), media_type="text/event-stream")

@app.get("/memories")
def list_memories(limit: int = 10):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT memory_id, session_id, kind, text, importance, created_at FROM app.memories ORDER BY created_at DESC LIMIT %s",
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

@app.delete("/memories/{session_id}")
def clear_memories(session_id: str):
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM app.memories WHERE session_id = %s",
            (session_id,),
        )
        deleted_rows = cur.rowcount
        conn.commit()
        cur.close()
        conn.close()
        print(f"Cleared {deleted_rows} memories for session {session_id}")
        return {"status": "success", "deleted_count": deleted_rows}
    except Exception as e:
        print(f"Error clearing memories: {e}")

        return {"status": "error", "message": str(e)}
