from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List
import httpx
import os

router = APIRouter()

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

SYSTEM_PROMPT = """You are TutorGate AI Study Assistant — a brilliant, encouraging tutor for Nigerian students (SS1–SS3, JAMB, university). Your tone is warm, clear, and motivating.

Rules:
- For maths/science problems, show step-by-step working with clear labels
- Reference Nigerian curriculum (WAEC, NECO, JAMB syllabi)
- Use simple language; avoid jargon unless explaining it
- Give practical exam tips when relevant
- Keep responses focused and well-structured
- Use emojis sparingly to highlight key points
- Always end with an encouraging line or a follow-up question"""

class Message(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    messages: List[Message]

@router.post("/chat")
async def ai_chat(body: ChatRequest):
    if not ANTHROPIC_API_KEY:
        raise HTTPException(500, "AI service not configured")

    # Keep last 10 messages to avoid token overflow
    messages = [{"role": m.role, "content": m.content} for m in body.messages[-10:]]

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-6",
                "max_tokens": 1000,
                "system": SYSTEM_PROMPT,
                "messages": messages,
            }
        )

    if resp.status_code != 200:
        raise HTTPException(502, f"AI service error: {resp.text}")

    data = resp.json()
    text = data.get("content", [{}])[0].get("text", "Sorry, I couldn't respond. Please try again.")
    return {"reply": text}
