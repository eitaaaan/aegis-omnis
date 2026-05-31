# -*- coding: utf-8 -*-
try: import ollama
except ImportError: ollama = None

MODEL_NAME = "gemma3:4b"

def check_connection() -> bool:
    if ollama is None: return False
    try:
        ollama.list()
        return True
    except: return False

def get_llm_opt(is_logic_mode: bool, text_len: int = 0, temp_override: float = None, stop_words: list = None) -> dict:
    ctx = 8192 if is_logic_mode or text_len > 1200 else 4096
    final_temp = temp_override if temp_override is not None else (0.18 if is_logic_mode else 0.78)
    stops = stop_words if stop_words else []
    if is_logic_mode: return dict(num_ctx=ctx, num_predict=4096, temperature=final_temp, top_k=30, top_p=0.86, repeat_penalty=1.28, stop=stops)
    return dict(num_ctx=ctx, num_predict=1800, temperature=final_temp, top_k=55, top_p=0.92, repeat_penalty=1.12, stop=stops)

def stream_response(messages: list, is_logic: bool, text_len: int, temp_override: float = None, stop_words: list = None) -> str:
    if not ollama: return ""
    opts = get_llm_opt(is_logic, text_len, temp_override, stop_words)
    full = ""
    try:
        for chunk in ollama.chat(model=MODEL_NAME, messages=messages, stream=True, options=opts):
            t = chunk["message"]["content"]
            print(t, end="", flush=True)
            full += t
        print()
    except Exception as e: print(f"\n[ERR] LLM: {e}")
    return full