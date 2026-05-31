# -*- coding: utf-8 -*-
import json
import os

class PersonaManager:
    def __init__(self, db_path="persona/db.json"):
        self.db_path = db_path
        self.personas = self._load_db()
        self.current_id = "2"  # デフォルトは S-01
        self.custom_persona = None

    def _load_db(self) -> dict:
        if not os.path.exists(self.db_path): return {}
        try:
            with open(self.db_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[ERR] ペルソナDBの読み込みに失敗しました: {e}")
            return {}

    def get_current_persona(self) -> dict:
        if self.custom_persona: return self.custom_persona
        return self.content_of(self.current_id)

    def content_of(self, per_id: str) -> dict:
        per_id = str(per_id)
        if per_id in self.personas: return self.personas[per_id]
        return self.personas.get("2", {"name": "S-01", "style": "助手", "first_person": "私"})

    def set_persona(self, arg: str) -> bool:
        arg = arg.strip()
        if not arg:
            self.current_id = "2"
            self.custom_persona = None
            return True
        if arg.isdigit() and arg in self.personas:
            self.current_id = arg
            self.custom_persona = None
            return True
        return False

    def set_custom_persona(self, name: str, style: str, first_person: str = "私"):
        self.custom_persona = {"name": name, "style": style, "first_person": first_person}

    def get_stop_words(self, user_name: str) -> list[str]:
        stop_words = [f"{user_name}:", f"{user_name}：", f"\n{user_name}", "\n/", "---", "==="]
        names = [p["name"] for p in self.personas.values()]
        if self.custom_persona: names.append(self.custom_persona["name"])
        for name in set(names):
            stop_words.extend([f"{name}:", f"{name}：", f"\n{name}"])
        return stop_words