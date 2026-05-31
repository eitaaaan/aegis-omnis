# -*- coding: utf-8 -*-
import os, base64
try: import ollama
except ImportError: ollama = None

VISION_MODEL = "llava"

def analyze_image(image_path: str, prompt: str) -> str:
    if not ollama: return "Ollamaがありません。"
    if not os.path.exists(image_path): return "画像がありません。"
    try:
        with open(image_path, "rb") as f: img_b64 = base64.b64encode(f.read()).decode("utf-8")
        resp = ollama.chat(model=VISION_MODEL, messages=[{"role": "user", "content": prompt, "images": [img_b64]}], stream=False)
        return resp.get("message", {}).get("content", "")
    except Exception as e: return f"エラー: {e}"