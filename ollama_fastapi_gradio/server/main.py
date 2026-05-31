# -*- coding: utf-8 -*-
"""FastAPI Backend for Aegis Omnis - Serves /chat endpoint for Gradio UI."""
import os, re, json, sys
from pathlib import Path

# Add parent directory to path so we can import core/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from pydantic import BaseModel, Field
from core.ollama_client import OllamaClient
from core.persona import default_persona_contract, dumps_persona_contract
from core.prompts import (
    PASS1_SYSTEM, PASS1_USER_TEMPLATE,
    PASS2_SYSTEM, PASS2_USER_TEMPLATE,
)
from core.rag import rag_retrieve, Evidence

app = FastAPI(title="Aegis Omnis API")

ollama = OllamaClient(base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"))
PASS1_MODEL = os.getenv("PASS1_MODEL", "gemma3:4b")
PASS2_MODEL = os.getenv("PASS2_MODEL", "gemma3:4b")


class ChatRequest(BaseModel):
    user_message: str
    conversation_summary: str = ""
    persona_id: str = "sample_hero"
    strictness: float = Field(default=0.7, ge=0.0, le=1.0)
    length: str = Field(default="normal", pattern="^(short|normal|long)$")


class EvidenceItem(BaseModel):
    source_id: str
    text: str


class ChatResponse(BaseModel):
    answer: str
    evidence_used: list[EvidenceItem]


def extract_json(raw: str) -> dict:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.MULTILINE)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return {
            "queries": [],
            "outline": [],
            "must_follow": [],
            "unknown_policy": "Say 不明 if uncertain.",
            "clarifying_question": None,
        }


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    persona = default_persona_contract()
    persona_json = dumps_persona_contract(persona)

    pass1_prompt = PASS1_USER_TEMPLATE.format(
        persona_contract_json=persona_json,
        conversation_summary=req.conversation_summary,
        user_message=req.user_message,
    )

    pass1_raw = await ollama.generate(
        model=PASS1_MODEL,
        system=PASS1_SYSTEM,
        prompt=pass1_prompt,
        temperature=0.1,
        top_p=0.9,
        num_predict=512,
    )

    plan = extract_json(pass1_raw)

    evidence_list = await rag_retrieve(plan.get("queries", []))

    must_follow = "\n".join(f"- {m}" for m in plan.get("must_follow", []))
    unknown_policy = plan.get("unknown_policy", "Say 不明 if uncertain.")
    outline = "\n".join(f"- {o}" for o in plan.get("outline", []))
    evidence_str = "\n".join(f"[{e.source_id}] {e.text}" for e in evidence_list) if evidence_list else "(no evidence retrieved)"

    length_hint = {
        "short": "Keep it concise (1-2 paragraphs).",
        "normal": "",
        "long": "Elaborate in detail (3+ paragraphs).",
    }

    pass2_system = PASS2_SYSTEM + "\n" + length_hint.get(req.length, "")
    pass2_prompt = PASS2_USER_TEMPLATE.format(
        persona_contract_json=persona_json,
        must_follow=must_follow,
        unknown_policy=unknown_policy,
        outline=outline,
        evidence_snippets=evidence_str,
        user_message=req.user_message,
    )

    answer = await ollama.generate(
        model=PASS2_MODEL,
        system=pass2_system,
        prompt=pass2_prompt,
        temperature=0.7 + (req.strictness - 0.5) * 0.3,
        top_p=0.9,
        num_predict=2048,
    )

    return ChatResponse(
        answer=answer.strip(),
        evidence_used=[EvidenceItem(source_id=e.source_id, text=e.text) for e in evidence_list],
    )


@app.get("/health")
async def health():
    return {"status": "ok", "model": PASS1_MODEL}
