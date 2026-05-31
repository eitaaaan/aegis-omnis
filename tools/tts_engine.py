# -*- coding: utf-8 -*-
import platform
import subprocess as S
import re

def text_to_speech(text: str):
    clean_text = re.sub(r'[^\w\sぁ-んァ-ヶ亜-熙]', '', text).strip()
    if not clean_text: return
    try:
        os_sys = platform.system()
        if os_sys == "Windows":
            cmd = f"Add-Type -AssemblyName System.Speech; (New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak('{clean_text}')"
            S.run(["PowerShell", "-Command", cmd], stdout=S.DEVNULL, stderr=S.DEVNULL)
        elif os_sys == "Darwin": S.run(["say", clean_text], stdout=S.DEVNULL, stderr=S.DEVNULL)
        else: S.run(["spd-say", clean_text], stdout=S.DEVNULL, stderr=S.DEVNULL)
    except: pass