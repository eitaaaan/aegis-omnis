#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# s01_midi.py — MIDI生成ハンドラ
from __future__ import annotations
from s01_config import *
from s01_rag import stream_response

# ===== MIDI GENERATION =====
MIDI_SECTIONS = {
    "short":  [("intro", 4), ("verse_A", 8), ("outro", 4)],
    "medium": [("intro", 4), ("verse_A", 8), ("chorus", 8), ("verse_B", 8), ("chorus", 8), ("outro", 4)],
    "long":   [("intro", 4), ("verse_A", 8), ("chorus", 8), ("bridge", 8),
               ("verse_B", 8), ("chorus", 8), ("solo", 8), ("chorus", 8), ("outro", 8)],
    "ultra":  [("intro", 16), ("verse_A", 18), ("chorus", 18), ("verse_B", 18),
               ("chorus", 18), ("bridge", 16), ("solo", 18), ("chorus", 18),
               ("interlude", 12), ("verse_C", 18), ("chorus", 18), ("bridge2", 16),
               ("solo2", 18), ("chorus", 18), ("buildup", 12), ("chorus_final", 18), ("outro", 16)],
}

def _midi_section_prompt(theme: str, section: str, bars: int, tempo: int, key: str) -> list[dict]:
    system = (
        f"You are a MIDI composer. Generate a '{section}' section for a song.\n"
        f"Theme: {theme} | Key: {key} major | Tempo: {tempo} BPM | Length: {bars} bars\n"
        f"Output ONLY a valid JSON array of note objects. No explanation.\n"
        f"Format: [{{\"pitch\":60,\"start\":0.0,\"duration\":0.5,\"velocity\":80}}, ...]\n"
        f"Rules: pitch 0-127, start beat position (max {bars * 4 - 0.1:.1f}), "
        f"duration in beats, velocity 40-110.\n"
        f"Generate {bars * 6} to {bars * 10} notes. Output ONLY the JSON array."
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": f"Generate '{section}' section ({bars} bars) for '{theme}' in {key} major at {tempo} BPM."}]

def _parse_midi_notes(raw: str) -> list[dict]:
    match = re.search(r'\[[\s\S]*?\]', raw)
    if not match: return []
    try:
        notes = json.loads(match.group(0))
        return [{"pitch": max(0, min(127, int(n["pitch"]))), "start": max(0.0, float(n["start"])),
                 "duration": max(0.1, float(n["duration"])), "velocity": max(1, min(127, int(n["velocity"])))}
                for n in notes if isinstance(n, dict) and "pitch" in n and "start" in n]
    except Exception: return []

def generate_midi_section(theme: str, section: str, bars: int, tempo: int, key: str) -> list[dict]:
    raw = stream_response(_midi_section_prompt(theme, section, bars, tempo, key), True, 200, silent=True, max_tokens=8000)
    notes = _parse_midi_notes(raw)
    if not notes:
        import random; scale = [60, 62, 64, 65, 67, 69, 71, 72]
        notes = [{"pitch": random.choice(scale), "start": i * 0.5, "duration": 0.4, "velocity": 75} for i in range(bars * 8)]
    return notes

def save_midi(all_sections: list[tuple[str, list[dict]]], tempo: int, path: str) -> bool:
    try: from midiutil import MIDIFile
    except ImportError: return False
    midi = MIDIFile(1)
    midi.addTempo(0, 0, tempo)
    offset = 0.0
    for _, notes in all_sections:
        if not notes: continue
        for n in notes: midi.addNote(0, 0, n["pitch"], n["start"] + offset, n["duration"], n["velocity"])
        offset += max(n["start"] + n["duration"] for n in notes) + 2.0
    with open(path, "wb") as f: midi.writeFile(f)
    return True

def handle_midi(arg: str) -> str:
    if not arg:
        return (f"{C['r']}usage: /midi <テーマ> [short|medium|long|ultra] [BPM] [キー]{C['w']}")
    parts = arg.split()
    length, tempo, key = "medium", 120, "C"
    rest_parts = []
    for p in parts:
        if p.lower() in ("short", "medium", "long", "ultra"): length = p.lower()
        elif p.isdigit() and 60 <= int(p) <= 240: tempo = int(p)
        elif re.match(r'^[A-G]b?$', p): key = p
        else: rest_parts.append(p)
    theme = " ".join(rest_parts) or "インストゥルメンタル"
    sections_plan = MIDI_SECTIONS[length]
    total_bars = sum(b for _, b in sections_plan)
    print(f"{C['c']}♩ MIDI生成: 『{theme}』{key}メジャー {tempo}BPM {length}({total_bars}小節){C['w']}")
    try: from midiutil import MIDIFile
    except ImportError: return f"{C['r']}midiutil未インストール: pip install midiutil{C['w']}"
    all_sections: list[tuple[str, list[dict]]] = []
    total_notes = 0
    for section, bars in sections_plan:
        print(f"  {C['dim']}[{section}] {bars}小節 生成中...{C['w']}", end="", flush=True)
        notes = generate_midi_section(theme, section, bars, tempo, key)
        all_sections.append((section, notes))
        total_notes += len(notes)
        print(f" {C['g']}{len(notes)}音 完了{C['w']}")
    safe_theme = re.sub(r'[^\w]', '_', theme)[:20]
    filename = f"midi_{safe_theme}_{int(time.time())}.mid"
    if save_midi(all_sections, tempo, filename):
        return f"{C['g']}♪ 保存完了: {filename} ({total_notes}音 / {total_bars}小節 / {length}){C['w']}"
    return f"{C['r']}MIDI保存失敗{C['w']}"

def play_singularity(query: str) -> str:
    if not query: return f"{C['r']}曲名を指定してください。{C['w']}"
    ytdl, mpv = shutil.which("yt-dlp"), shutil.which("mpv")
    if not ytdl or not mpv: return f"{C['y']}yt-dlp と mpv が必要です。{C['w']}"
    out_file = f"ytdl_y_{os.getpid()}.wav"
    try:
        r = S.run([ytdl, "-x", "--audio-format", "wav", "-o", out_file, f"ytsearch1:{query}"], capture_output=True, text=True, timeout=60)
        if r.returncode != 0: return f"{C['r']}failed: {r.stderr[:200]}{C['w']}"
        if os.path.exists(out_file):
            S.Popen([mpv, "--no-video", out_file], stdout=S.DEVNULL, stderr=S.DEVNULL)
            return f"{C['g']}再生開始: {query}{C['w']}"
        return f"{C['r']}file not found{C['w']}"
    except S.TimeoutExpired: return f"{C['r']}timeout{C['w']}"
    except Exception as e: return f"{C['r']}error: {e}{C['w']}"


# ===== ローカルRAG: ファイル取り込み・オフライン推論 =====
