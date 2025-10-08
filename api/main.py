import os
import psycopg2
import json
import uuid
from typing import List
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from google import genai
import contextlib

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

@contextlib.contextmanager
def get_conn(schema: str = "public"):
    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn.cursor() as cur:
            cur.execute(f"SET search_path TO {schema}, public;")
        yield conn
    finally:
        conn.close()

class ChatRequest(BaseModel):
    session_id: str
    prompt: str

class ConsolidateRequest(BaseModel):
    user_id: str
    session_ids: List[str]

def get_embedding(text: str) -> List[float]:
    if not text:
        return []
    try:
        result = client.models.embed_content(model="models/text-embedding-004", contents=text)
        emb = result.embeddings[0].values
        return emb + [0.0] * 768
    except Exception as e:
        print(f"Error generating embedding: {e}")
        return []

def get_recent_business_context():
    with get_conn("domain") as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 
                    c.name AS customer_name, 
                    c.industry,
                    so.title AS order_title, 
                    so.status, 
                    so.created_at
                FROM domain.customers c
                JOIN domain.sales_orders so ON so.customer_id = c.customer_id
                ORDER BY so.created_at DESC
                LIMIT 5
            """)
            rows = cur.fetchall()
    if not rows:
        return "No recent data found."
    
    lines = [
        f"{name} ({industry}) — {order_title} [{status}] created {created_at:%Y-%m-%d}"
        for name, industry, order_title, status, created_at in rows
    ]
    return "Recent business data:\n" + "\n".join(lines)

def add_chat_event_db(session_id: str, role: str, content: str):
    with get_conn("app") as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO app.chat_events (session_id, role, content) VALUES (%s, %s, %s)",
                (session_id, role, content),
            )
            conn.commit()

def create_memory_db(session_id: str, text: str, importance: float = 0.5):
    embedding = get_embedding(text)
    if not embedding:
        print("Skipping memory creation due to embedding failure.")
        return
        
    with get_conn("app") as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO app.memories (session_id, kind, text, importance, embedding) VALUES (%s, %s, %s, %s, %s)",
                (session_id, 'reflection', text, importance, embedding),
            )
            conn.commit()
    print(f"Memory created for session {session_id}: {text}")

def convert_to_gemini_contents(history, system_instruction: str, user_prompt: str):
    contents = []
    if system_instruction:
        contents.append({"role": "user", "parts": [{"text": system_instruction}]})
    for role, content in history:
        role = "model" if role == "assistant" else "user"
        contents.append({"role": role, "parts": [{"text": content}]})
    contents.append({"role": "user", "parts": [{"text": user_prompt}]})
    return contents

app = FastAPI(title="LLM Memory API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
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

def maybe_add_domain_entry(session_id: str, user_prompt: str, assistant_response: str):
    if not client:
        return
    
    try:
        system_prompt = """
        You are a structured data extraction agent.
        Based on the following conversation, determine if there are any NEW or UPDATED business facts relevant to the company's domain database.
        Respond ONLY in JSON or the string "NONE".
        
        Expected JSON schema example:
        {
            "customers": [
                {"name": "Acme Corp", "industry": "Manufacturing"}
            ],
            "sales_orders": [
                {"customer_name": "Acme Corp", "title": "Order for 100 widgets", "status": "pending"}
            ]
        }
        Respond "NONE" if no relevant updates exist.
        """

        conversation_summary = f"User: {user_prompt}\nAssistant: {assistant_response}"
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[{"role": "user", "parts": [{"text": system_prompt + '\n\n' + conversation_summary}]}]
        )

        text = response.text.strip()
        if not text or text.upper() == "NONE":
            print("No new domain data detected.")
            return

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            print("Gemini output not valid JSON, skipping domain update.")
            return

        with get_conn("domain") as conn:
            with conn.cursor() as cur:
                if "customers" in data:
                    for c in data["customers"]:
                        cur.execute("""
                            INSERT INTO domain.customers (name, industry)
                            VALUES (%s, %s)
                            ON CONFLICT (name) DO NOTHING;
                        """, (c.get("name"), c.get("industry")))

                if "sales_orders" in data:
                    for o in data["sales_orders"]:
                        cur.execute("SELECT customer_id FROM domain.customers WHERE name = %s", (o.get("customer_name"),))
                        res = cur.fetchone()
                        if not res:
                            print(f"Skipping order for unknown customer {o.get('customer_name')}")
                            continue
                        customer_id = res[0]

                        cur.execute("""
                            INSERT INTO domain.sales_orders (customer_id, title, status)
                            VALUES (%s, %s, %s)
                            ON CONFLICT DO NOTHING;
                        """, (customer_id, o.get("title"), o.get("status")))

                conn.commit()
        print("Domain DB updated successfully.")
    except Exception as e:
        print(f"Error updating domain DB: {e}")


@app.post("/chat")
async def chat(req: ChatRequest):
    if not GOOGLE_API_KEY:
        raise HTTPException(status_code=500, detail="Gemini client not configured.")

    add_chat_event_db(req.session_id, 'user', req.prompt)

    with get_conn("app") as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT role, content FROM app.chat_events WHERE session_id = %s ORDER BY created_at DESC LIMIT 10", (req.session_id,))
            history = cur.fetchall()[::-1]

            cur.execute("SELECT text FROM app.memories WHERE session_id = %s ORDER BY created_at DESC LIMIT 5", (req.session_id,))
            memories = cur.fetchall()

    memory_str = "Key memories from this session:\n" + "\n".join([f"- {m[0]}" for m in memories]) if memories else "No prior memories from this session."
    domain_context = get_recent_business_context()

    print(memory_str)

    system_instruction = f"You are a helpful assistant.\n{memory_str}. Use the following company data to inform your responses: {domain_context}"
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
            maybe_add_domain_entry(req.session_id, req.prompt, full_response)
            yield f"data: {json.dumps({'status': 'done'})}\n\n"
        except Exception as e:
            print(f"Error during Gemini stream: {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(response_streamer(), media_type="text-event-stream")

@app.get("/memories")
def list_memories(session_id: str, limit: int = 10):
    with get_conn("app") as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT memory_id, session_id, kind, text, importance, created_at 
                FROM app.memories 
                WHERE session_id = %s ORDER BY created_at DESC LIMIT %s
                """,
                (session_id, limit,),
            )
            rows = cur.fetchall()
    return [
        {
            "memory_id": r[0],
            "session_id": str(r[1]),
            "kind": r[2],
            "text": r[3],
            "importance": float(r[4]),
            "created_at": r[5].isoformat(),
        }
        for r in rows
    ]

@app.delete("/memories/{session_id}")
def clear_session_memories(session_id: str):
    try:
        with get_conn("app") as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM app.memories WHERE session_id = %s", (session_id,))
                deleted_rows = cur.rowcount
        print(f"Cleared {deleted_rows} memories for session {session_id}")
        return {"status": "success", "deleted_count": deleted_rows}
    except Exception as e:
        print(f"Error clearing memories: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/consolidate")
async def consolidate_memories(req: ConsolidateRequest):
    if not client:
        raise HTTPException(status_code=500, detail="Gemini client not configured.")
        
    if not req.session_ids:
        return {"status": "success", "message": "No session IDs provided to consolidate."}

    try:
        with get_conn("app") as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT role, content FROM app.chat_events WHERE session_id::text = ANY(%s) ORDER BY created_at",
                    (req.session_ids,)
                )
                full_history = cur.fetchall()
        
        if not full_history:
             return {"status": "success", "message": "No chat history found for the provided sessions."}

        conversation_text = "\n".join([f"{role}: {content}" for role, content in full_history])
        prompt = f"Please provide a concise, high-level summary of the key topics, facts, and user preferences from the following conversation history:\n\n{conversation_text}"
        
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )
        summary_text = response.text.strip()
        
        summary_embedding = get_embedding(summary_text)

        with get_conn("app") as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO app.memory_summaries (user_id, session_window, summary, embedding) VALUES (%s, %s, %s, %s)",
                    (req.user_id, len(req.session_ids), summary_text, summary_embedding)
                )

        return {"status": "success", "user_id": req.user_id, "summary": summary_text}
    except Exception as e:
        print(f"Error during consolidation: {e}")
        raise HTTPException(status_code=500, detail=str(e))