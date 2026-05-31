# -*- coding: utf-8 -*-
from llm_engine.ollama_client import stream_response

def run_character_conversation(id1: str, id2: str, theme: str, persona_manager):
    p1, p2 = persona_manager.content_of(id1), persona_manager.content_of(id2)
    print(f"\n\033[93m=== 自動対話: {p1['name']} vs {p2['name']} ({theme}) ===\033[0m\n")
    ms1, ms2 = [], []
    last_reply = f"ねえ、「{theme}」についてどう思う？"
    
    for _ in range(3):
        print(f"\033[96m{p1['name']}\033[0m: ", end="", flush=True)
        s1 = {"role": "system", "content": f"あなたは{p1['name']}。口調:{p1['style']} 相手は{p2['name']}。手短に会話せよ。"}
        ms1.append({"role": "user", "content": last_reply})
        last_reply = stream_response([s1] + ms1, is_logic=False, text_len=100)
        ms1.append({"role": "assistant", "content": last_reply})
        ms2.append({"role": "user", "content": last_reply})
        
        print(f"\033[95m{p2['name']}\033[0m: ", end="", flush=True)
        s2 = {"role": "system", "content": f"あなたは{p2['name']}。口調:{p2['style']} 相手は{p1['name']}。手短に会話せよ。"}
        last_reply = stream_response([s2] + ms2, is_logic=False, text_len=100)
        ms2.append({"role": "assistant", "content": last_reply})
        ms1.append({"role": "user", "content": last_reply})