# -*- coding: utf-8 -*-
def build_system_prompt(mode: str, persona: dict, data: str = "", key: str = "", keywords: list = None) -> dict:
    first_person = persona.get("first_person", "私")
    common = f"あなたは「{persona['name']}」。一人称は「{first_person}」。口調: {persona['style']}\n地の文やAI的宣言は禁止。セリフのみ出力せよ。"
    if keywords: common += f"\n【現在の会話の文脈】: {', '.join(keywords[-5:])}"

    templates = {
        "d": f"{common}\nカジュアルな雑談として返答せよ。",
        "a": f"{common}\n絶対ルール: 以下の<FACT>のみ使い解説せよ。捏造禁止。\nテーマ: {key}\n<FACT>\n{data}\n</FACT>"
    }
    return {"role": "system", "content": templates.get(mode, templates["d"])}