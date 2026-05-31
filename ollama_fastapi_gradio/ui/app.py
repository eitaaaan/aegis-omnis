import os

import gradio as gr
import httpx
from dotenv import load_dotenv

load_dotenv()
FASTAPI_URL = os.getenv("FASTAPI_URL", "http://localhost:8000").rstrip("/")

def chat(user_message: str, strictness: float, length: str):
    if not user_message.strip():
        return "", ""

    payload = {
        "user_message": user_message,
        "conversation_summary": "",
        "persona_id": "sample_hero",
        "strictness": strictness,
        "length": length,
    }

    with httpx.Client(timeout=120) as client:
        r = client.post(f"{FASTAPI_URL}/chat", json=payload)
        r.raise_for_status()
        data = r.json()

    evidence = data.get("evidence_used") or []
    if not evidence:
        ev_text = "(根拠: まだ未実装 / 参照なし)"
    else:
        ev_text = "\n\n".join([f"- {e['source_id']}\n  {e['text']}" for e in evidence])

    return data.get("answer", ""), ev_text

with gr.Blocks(title="Local AI (Ollama) - Thin UI") as demo:
    gr.Markdown("## Local AI (Ollama) — FastAPI(core) + Gradio(UI)")
    user_message = gr.Textbox(label="User message", lines=4, placeholder="ここに入力")

    with gr.Row():
        strictness = gr.Slider(0.0, 1.0, value=0.7, step=0.05, label="厳密さ（根拠優先）")
        length = gr.Radio(["short", "normal", "long"], value="normal", label="長さ")

    run = gr.Button("Run")
    answer = gr.Textbox(label="Answer", lines=10)
    evidence = gr.Textbox(label="Evidence", lines=8)

    run.click(fn=chat, inputs=[user_message, strictness, length], outputs=[answer, evidence])

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860)
