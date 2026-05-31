#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# s01_persona.py — ペルソナ管理・状態保存・メモリ・会話履歴ユーティリティ
from __future__ import annotations
from s01_config import *
from s01_learning import *

def get_persona(per_id) -> dict:
    if CUSTOM_PERSONA is not None: return CUSTOM_PERSONA
    return PERSONA_MAP.get(per_id, PERSONA_MAP[2])

C = {
    "r": "\033[91m", "g": "\033[92m", "y": "\033[93m",
    "b": "\033[94m", "p": "\033[95m", "c": "\033[96m",
    "w": "\033[0m", "bold": "\033[1m", "dim": "\033[2m",
}

BANNER = (
    f"{C['c']}{C['bold']}\nPROJECT AEGIS [v128.1 ENHANCED]{C['w']}\n"
    f"  CORE: {MODEL_NAME} | RAG: MULTI-SOURCE | 2PASS: ACTIVE | LEARN: ON\n"
    f"  /h コマンド一覧 | /s 1〜24 西洋哲学者 | /s お嬢様 など自由入力でWeb検索生成\n"
)

HELP_TEXT = "\n".join([
    f"{C['y']}=== コマンド一覧 (v128.1 ENHANCED) ==={C['w']}",
    f"  {C['c']}/a <キーワード>{C['w']}     RAG+2Pass分析",
    f"  {C['c']}/w <テキスト>{C['w']}       要約  {C['c']}/p <テキスト>{C['w']}       校正",
    f"  {C['c']}/c <仕様>{C['w']}           コード設計  {C['c']}/t <テキスト>{C['w']}       超訳",
    f"  {C['c']}/e <テキスト>{C['w']}       英訳  {C['c']}/sum <テキスト>{C['w']}       長文要約",
    f"  {C['c']}/r <状況>{C['w']}           ロールプレイ  {C['c']}/rend{C['w']}           RP終了",
    f"  {C['c']}/q <目標>{C['w']}           クエスト化  {C['c']}/q list/done/show{C['w']} 管理",
    f"  {C['c']}/m add/list/find/del{C['w']} メモ管理",
    f"  {C['c']}/dict add <用語> | <説明>{C['w']} 辞書登録",
    f"  {C['c']}/dict <用語>{C['w']}          辞書検索",
    f"  {C['c']}/elab <内容>{C['w']}         深層推論（比喩・例えで説明）",
    f"  {C['c']}/doc add <タイトル> | <本文>{C['w']} 文書保存",
    f"  {C['c']}/doc think <タイトル>{C['w']}  保存文書を深層推論",
    f"  {C['c']}/l <曲名>{C['w']}           歌詞検索  {C['c']}/y <曲名>{C['w']}           音楽再生",
    f"  {C['c']}/midi <テーマ> [short|medium|long] [BPM] [キー]{C['w']} MIDI生成",
    f"  {C['c']}/doctor{C['w']}             環境診断  {C['c']}/debug{C['w']}              RAG診断",
    f"  {C['c']}/power low|mid|high|ultra{C['w']} 推論強度  {C['c']}/optimizer{C['w']}         最適化状態",
    f"  {C['c']}/tool <query>{C['w']}        ツール使用（計算・検索・ファイル操作）",
    f"  {C['c']}/vec{C['w']}                ベクトル記憶状態",
    f"  {C['c']}/stats{C['w']}              セッション統計  {C['c']}/history [keyword]{C['w']}   履歴検索",
    f"  {C['c']}/export [md|json|txt]{C['w']} 会話出力  {C['c']}/template add/list/del{C['w']} テンプレート",
    f"  {C['c']}/tts <text>{C['w']}          音声読み上げ  {C['c']}/tr <lang> <text>{C['w']}    翻訳",
    f"  {C['c']}/reference{C['w']}         他AI参照 自己評価  {C['c']}/stop{C['w']}              一時ファイル削除",
    f"  {C['c']}/s [1-24]{C['w']}          西洋哲学者に切替（1=ソクラテス〜24=後期ウィトゲンシュタイン）",
    f"  {C['c']}/s <任意名>{C['w']}        Web検索でペルソナ自動生成（例: お嬢様 / 忍者 / ニュートン）",
    f"  {C['c']}/s save <名前>{C['w']}     ペルソナ保存  {C['c']}/s load <名前>{C['w']}    ペルソナロード",
    f"  {C['c']}/s list{C['w']}            保存一覧  {C['c']}/s del <名前>{C['w']}      保存削除  {C['c']}/g{C['w']} 履歴クリア",
    f"  {C['c']}/h{C['w']}                  ヘルプ  {C['c']}/learn{C['w']}              学習状態表示",
    f"",
    f"  {C['c']}/ety <英単語>{C['w']}       語源図鑑（接頭辞・語根・接尾辞を色分け解説）",
    f"  {C['c']}/img <prompt>{C['w']}        画像生成（PIL数学アート）",
    f"  {C['c']}/convert <fmt> <from> <to>{C['w']}  形式変換（md2html, csv2json 等）",
    f"  {C['c']}/qr <text>{C['w']}           QRコード生成",
    f"  {C['c']}/color <hex>{C['w']}         色情報表示",
    f"  {C['c']}/sysinfo{C['w']}            システム情報表示",
    f"  {C['c']}/rename <old> <new>{C['w']}   ファイル名変更",
    f"  {C['c']}/batch <cmd> <path>{C['w']}   ファイル一括処理",
    f"  {C['c']}/chart <data>{C['w']}        簡易チャート生成（棒/折れ線/円）",
    f"  {C['c']}/note <text>{C['w']}         クイックノート",
    f"  {C['c']}/timer <seconds>{C['w']}     タイマー",
    f"  {C['c']}/calc <expression>{C['w']}   高度計算機",
    f"  {C['c']}/kb add <ファイル>{C['w']}    テキスト/PDFをローカルRAGに取り込む",
    f"  {C['c']}/kb ask <質問>{C['w']}        ローカル知識ベースでオフライン推論",
    f"  {C['c']}/kb search <キーワード>{C['w']} ローカルRAG検索（ネット不要）",
    f"  {C['c']}/kb list / del{C['w']}        知識ベース管理",
    f"  {C['c']}/spi{C['w']}                SPI/玉手箱 対策（/spi 模擬 で10問連続）",
    f"  {C['c']}/comp <ID> <ID> [テーマ]{C['w']}  ヘーゲル弁証法対話（哲学者/カジュアル/ビジネス自動判定）",
    f"  {C['c']}/split <ID or 名前> [テーマ]{C['w']} 1ペルソナをテーゼ/アンチテーゼに分解して内的弁証法",
    f"  {C['c']}/chess{C['w']}              ♟ チェス（完全ルール実装・ターミナル対戦）\n              例: /chess easy  /chess middle  /chess hard  /chess very_hard",
    f"  {C['c']}/shogi{C['w']}              将棋（本将棋・curses UI・AI対戦対応）\n              例: /shogi easy  /shogi middle  /shogi hard  /shogi very_hard",
    f"  {C['c']}/mj{C['w']}                🀄 本格麻雀（ブラウザ起動・AI対戦・役/符計算完全実装）\n              例: /mj        → 4人麻雀東風戦\n                  /mj 3     → 3人麻雀\n                  /mj tonpu → 4人麻雀東南戦",
    f"  {C['c']}exit / 終了{C['w']}          終了",
])

class SystemSpinner:
    STAGES = {
        "default": (["[▓░░░░]", "[▓▓░░░]", "[▓▓▓░░]", "[▓▓▓▓░]", "[▓▓▓▓▓]"], C['c']),
        "rag":     (["[WEB░░]", "[WEB▓░]", "[WEB▓▓]", "[NET▓▓]", "[DONE]"], C['b']),
        "pass1":   (["[P1░░░]", "[P1▓░░]", "[P1▓▓░]", "[P1▓▓▓]", "[FACT]"], C['y']),
        "pass2":   (["[P2░░░]", "[P2▓░░]", "[P2▓▓░]", "[P2▓▓▓]", "[DONE]"], C['p']),
        "img":     (["[IMG░░]", "[IMG▓░]", "[IMG▓▓]", "[REND░]", "[DONE]"], C['g']),
    }
    def __init__(self, message: str = "処理中...", stage: str = "default"):
        self.message, self.stage, self.is_running = message, stage, False
        self._thread, self._elapsed = None, 0.0
        self._stopped = False
    def _animate(self):
        frames, color = self.STAGES.get(self.stage, self.STAGES["default"])
        start = time.time()
        try:
            for frame in itertools.cycle(frames):
                if not self.is_running: break
                elapsed = time.time() - start
                sys.stdout.write(f"\r{color}{frame}{C['w']} {C['dim']}{self.message}{C['w']} {C['dim']}({elapsed:.1f}s){C['w']}")
                sys.stdout.flush()
                time.sleep(0.12)
        except Exception: pass
        self._elapsed = time.time() - start
        try: sys.stdout.write("\r\033[K"); sys.stdout.flush()
        except Exception: pass
    def start(self):
        if self._stopped: return
        if self._thread and self._thread.is_alive(): return
        self.is_running = True
        self._thread = threading.Thread(target=self._animate, daemon=True)
        self._thread.start()
    def stop(self) -> float:
        self.is_running = False
        self._stopped = True
        if self._thread:
            try: self._thread.join(timeout=1.0)
            except Exception: pass
        return self._elapsed
    def __enter__(self): self.start(); return self
    def __exit__(self, *exc): self.stop()

def sanitize(txt: str) -> str:
    clean = re.sub(r'[\ud800-\udfff]', '', str(txt))
    return clean.encode("utf-8", "ignore").decode("utf-8")

def sanitize_obj(value):
    if isinstance(value, str):
        return sanitize(value)
    if isinstance(value, list):
        return [sanitize_obj(v) for v in value]
    if isinstance(value, tuple):
        return tuple(sanitize_obj(v) for v in value)
    if isinstance(value, dict):
        return {sanitize(k): sanitize_obj(v) for k, v in value.items()}
    return value

def normalize_input(txt: str) -> str:
    clean = re.sub(r'[\ud800-\udfff]', '', str(txt))
    clean = unicodedata.normalize("NFKC", clean)
    clean = re.sub(r'<(RAG_DATA|FACT|system|SYSTEM)>', r'&lt;\1&gt;', clean)
    clean = re.sub(r'[\s\u200b\u200c\u200d\ufeff]+', ' ', clean)
    return clean.strip()

def PurgeEvidence():
    removed = 0
    for p in ["voice_*.wav", "ytdl_*.wav", "*.tmp"]:
        for f in glob.glob(p):
            try: os.remove(f); removed += 1
            except OSError: pass
    if platform.system() != "Windows": S.run(["pkill", "-9", "mpv"], stderr=S.DEVNULL)
    print(f"{C['y']}一時ファイル {removed} 件を削除しました。{C['w']}")

def now_stamp() -> str: return time.strftime("%Y-%m-%d %H:%M")

_state_cache: dict | None = None
_state_cache_time: float = 0.0
_STATE_CACHE_TTL = 5.0

def load_state() -> dict:
    global _state_cache, _state_cache_time
    now = time.time()
    if _state_cache is not None and now - _state_cache_time < _STATE_CACHE_TTL:
        return _state_cache
    default: dict = {"memo": [], "quests": [], "keywords": []}
    stale_tmp = STATE_FILE + ".tmp"
    if os.path.exists(stale_tmp):
        try: os.remove(stale_tmp)
        except Exception: pass
    if not os.path.exists(STATE_FILE):
        _state_cache, _state_cache_time = default, now
        return default
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            raw = f.read()
        if not raw or not raw.strip():
            _state_cache, _state_cache_time = default, now
            return default
        data = sanitize_obj(json.loads(raw))
        if not isinstance(data, dict):
            _state_cache, _state_cache_time = default, now
            return default
        for key in ("memo", "quests", "keywords", "dict", "docs"): data.setdefault(key, [])
        data.setdefault("learning", {})
        _state_cache, _state_cache_time = data, now
        return data
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        try:
            bak = STATE_FILE + ".bak"
            shutil.copy2(STATE_FILE, bak)
            print(f"{C['y']}状態ファイル破損. バックアップ作成: {bak}{C['w']}")
        except Exception: pass
        _state_cache, _state_cache_time = default, now
        return default

def save_state(state: dict) -> None:
    global _state_cache, _state_cache_time
    tmp = STATE_FILE + ".tmp"
    try:
        safe_state = sanitize_obj(state)
        with open(tmp, "w", encoding="utf-8") as f: json.dump(safe_state, f, ensure_ascii=False, indent=2)
        os.replace(tmp, STATE_FILE)
        _state_cache, _state_cache_time = safe_state, time.time()
    except Exception:
        try: os.remove(tmp)
        except Exception: pass

def persist_learning():
    state = load_state()
    state["learning"] = {
        "interaction_log": INTERACTION_LOG[-100:],
        "learning_stats": LEARNING_STATS,
        "prompt_performance": {k: v[-50:] for k, v in PROMPT_PERFORMANCE.items()},
        "param_performance": {k: v for k, v in PARAM_PERFORMANCE.items()},
        # ★[修正C] ユーザー指摘・自動最適化指示を永続化
        "prompt_optimizations": {k: v for k, v in PROMPT_OPTIMIZATIONS.items()},
        "optimization_history": OPTIMIZATION_HISTORY[-50:],
    }
    state["power_mode"] = POWER_MODE
    # ペルソナキャッシュも永続化（Web取得済みを保存）
    state["persona_cache"] = {k: v for k, v in PERSONA_STYLE_CACHE.items()}
    save_state(state)

def restore_learning():
    global INTERACTION_LOG, LEARNING_STATS, PROMPT_PERFORMANCE, PARAM_PERFORMANCE, POWER_MODE
    global PROMPT_OPTIMIZATIONS, OPTIMIZATION_HISTORY
    state = load_state()
    lr = state.get("learning", {})
    INTERACTION_LOG = lr.get("interaction_log", [])
    LEARNING_STATS.update(lr.get("learning_stats", {}))
    for k, v in lr.get("prompt_performance", {}).items(): PROMPT_PERFORMANCE[k] = v
    for k, v in lr.get("param_performance", {}).items(): PARAM_PERFORMANCE[k] = v
    saved = state.get("power_mode")
    if saved in ("low", "mid", "high", "ultra"): POWER_MODE = saved
    # ペルソナキャッシュを復元（前回Web取得済みをそのまま使い回せる）
    for k, v in state.get("persona_cache", {}).items():
        if isinstance(v, dict) and "name" in v and "style" in v:
            PERSONA_STYLE_CACHE[k] = v
    # ★[修正C] ユーザー指摘・プロンプト最適化指示を復元（ペルソナ単位ネスト構造）
    saved_opts = lr.get("prompt_optimizations", {})
    for pkey, bucket in saved_opts.items():
        if isinstance(bucket, dict):
            # dict[str, list[str]] 形式のみ受け入れ
            clean = {cat: [d for d in lst if isinstance(d, str)]
                     for cat, lst in bucket.items() if isinstance(lst, list)}
            if clean:
                PROMPT_OPTIMIZATIONS[pkey] = clean
        elif isinstance(bucket, list):
            # 旧形式（カテゴリ→list[str]）を global バケツに移行
            PROMPT_OPTIMIZATIONS.setdefault("global", {}).setdefault(pkey, []).extend(
                [d for d in bucket if isinstance(d, str)]
            )
    OPTIMIZATION_HISTORY = lr.get("optimization_history", [])
    total_directives = sum(len(v) for bucket in PROMPT_OPTIMIZATIONS.values()
                           if isinstance(bucket, dict) for v in bucket.values())
    if total_directives:
        print(f"{C['dim']}[学習] プロンプト指示 {total_directives}件 復元済み{C['w']}")

# ===== ペルソナ セーブ/ロード =====
def save_persona(slot_name: str, persona: dict) -> bool:
    if not slot_name or not persona: return False
    state = load_state()
    slots: dict = state.setdefault("saved_personas", {})
    slots[slot_name] = {
        "name":         persona.get("name", slot_name),
        "style":        persona.get("style", ""),
        "first_person": persona.get("first_person", "私"),
        "_web":         persona.get("_web", False),
        "saved_at":     now_stamp(),
    }
    save_state(state)
    return True

def load_persona(slot_name: str) -> dict | None:
    slots = load_state().get("saved_personas", {})
    return slots.get(slot_name)

def delete_persona(slot_name: str) -> bool:
    state = load_state()
    slots = state.get("saved_personas", {})
    if slot_name not in slots: return False
    del slots[slot_name]
    save_state(state)
    return True

def list_personas() -> dict:
    return load_state().get("saved_personas", {})

def _normalize_observed_subject(text: str) -> str:
    """Keep remembered user/subject labels from drifting to the assistant persona name."""
    if not text:
        return ""
    return re.sub(r"(?i)(?<![A-Za-z0-9_-])S-?01(?=\s*[:：は])", OBSERVED_SUBJECT_NAME, text)

def memory_context(limit: int = 8, query: str = "") -> str:
    parts = []
    memos = load_state().get("memo", [])[-limit:]
    if memos:
        parts.append("\n".join(f"- {_normalize_observed_subject(m.get('text', ''))}" for m in memos if m.get("text")))
    # queryがある場合はそれで検索。ない場合はKEYWORD_MEMORYの直近2件のみ使用
    # (古い話題キーワード全部で検索すると文脈ブリードの原因になる)
    if query:
        vec_query = query
    elif KEYWORD_MEMORY:
        vec_query = " ".join(KEYWORD_MEMORY[-2:])
    else:
        vec_query = ""
    vec_hits = vector_search(vec_query, n=3) if vec_query else []
    if vec_hits:
        parts.append("\n".join(f"• {_normalize_observed_subject(h[:200])}" for h in vec_hits))
    state = load_state()
    if state.get("dict") and query:
        # queryが明示的にある時だけ辞書を参照 (KEYWORD_MEMORYからの辞書引きはブリード源)
        hits = [e for e in state["dict"] if any(w in e["term"] for w in query.split() if len(w) >= 2)]
        if hits:
            parts.append("【辞書】\n" + "\n".join(f"• {e['term']}: {e['def'][:150]}" for e in hits[:5]))
    return "\n\n".join(parts)

def extract_keywords(text: str, top_n: int = 5) -> list[str]:
    patterns = [r'[ァ-ヶー]{3,}', r'[一-龯]{2,}', r'[A-Za-z]{4,}']
    words = []
    for pat in patterns: words.extend(re.findall(pat, text))
    stop = {'について', 'する', 'ある', 'いる', 'です', 'ます', 'こと', 'もの', 'ため'}
    counter = Counter(w for w in words if w not in stop and len(w) >= 2)
    return [w for w, _ in counter.most_common(top_n)]

def update_keyword_memory(text: str) -> None:
    global KEYWORD_MEMORY
    noise = {'debug', 'rend', 'exit', '終了', 'help', 'list', 'add', 'del', 'find', 'done', 'show', 'fast', 'stop', 'power', 'low', 'mid', 'high', 'ultra', 'doctor'}
    new_kw = [w for w in extract_keywords(text) if w.lower() not in noise and len(w) >= 2]
    # 最大6件に絞る。古い話題のキーワードがシステムプロンプトに残留しないようにする
    KEYWORD_MEMORY = list(dict.fromkeys(KEYWORD_MEMORY + new_kw))[-6:]

def analyze_feedback(user_input: str) -> float:
    norm = normalize_for_match(user_input)
    pos_score = sum(2 for p in FEEDBACK_PATTERNS['positive'] if p in norm)
    neg_score = sum(2 for n in FEEDBACK_PATTERNS['negative'] if n in norm)
    if pos_score > neg_score: return min(1.0, pos_score * 0.25)
    elif neg_score > 0: return max(-1.0, -neg_score * 0.25)
    for n in FEEDBACK_PATTERNS['neutral']:
        if n in norm: return 0.1
    return 0.0

def log_interaction(user_input: str, response: str, mode: str, feedback: float):
    global LEARNING_STATS
    LEARNING_STATS["total_interactions"] += 1
    if feedback > 0.3: LEARNING_STATS["positive_count"] += 1
    elif feedback < -0.3: LEARNING_STATS["negative_count"] += 1
    entry = {"time": time.time(), "input": sanitize(user_input[:200]), "response_len": len(response), "mode": mode, "feedback": round(feedback, 2)}
    INTERACTION_LOG.append(entry)
    if len(INTERACTION_LOG) > 200: INTERACTION_LOG[:] = INTERACTION_LOG[-200:]
    mode = mode or "d"
    if mode not in PROMPT_PERFORMANCE: PROMPT_PERFORMANCE[mode] = []
    PROMPT_PERFORMANCE[mode].append(feedback)
    if len(PROMPT_PERFORMANCE[mode]) > 100: PROMPT_PERFORMANCE[mode] = PROMPT_PERFORMANCE[mode][-100:]

def get_best_temp(mode: str) -> float | None:
    if mode not in PARAM_PERFORMANCE or not PARAM_PERFORMANCE[mode]: return None
    best_score = -999
    best_temp = None
    for temp_str, scores in PARAM_PERFORMANCE[mode].items():
        if scores:
            avg = sum(scores) / len(scores)
            if avg > best_score:
                best_score = avg
                try: best_temp = float(temp_str)
                except ValueError: best_temp = None
    return best_temp

def update_param_performance(mode: str, temp: float, feedback: float):
    mode = mode or "d"
    if mode not in PARAM_PERFORMANCE: PARAM_PERFORMANCE[mode] = {}
    key = f"{temp:.2f}"
    if key not in PARAM_PERFORMANCE[mode]: PARAM_PERFORMANCE[mode][key] = []
    PARAM_PERFORMANCE[mode][key].append(feedback)
    if len(PARAM_PERFORMANCE[mode][key]) > 50: PARAM_PERFORMANCE[mode][key] = PARAM_PERFORMANCE[mode][key][-50:]

def optimize_prompt_template() -> str:
    best_mode = None; best_avg = -999
    for mode, scores in PROMPT_PERFORMANCE.items():
        if len(scores) >= 3:
            avg = sum(scores) / len(scores)
            if avg > best_avg: best_avg, best_mode = avg, mode
    if best_mode and best_avg > 0.3: return f" [学習: {best_mode}モード最適 ({best_avg:.1f})]"
    return ""

def cleanup_knowledge():
    now = time.time()
    with _RAG_LOCK:
        expired = [k for k, (ts, content, access_count, confidence) in list(RAG_CACHE.items())
                   if now - ts > 1800 and access_count < 1 or now - ts > 7200 or confidence < 0.4 and access_count == 0]
        for key in expired: del RAG_CACHE[key]
    return len(expired)

def self_evaluate_response(response: str, query: str) -> tuple[float, list[str]]:
    issues = []
    if not response or len(response.strip()) < 5: issues.append("empty_or_too_short")
    if detect_repetition(response): issues.append("repetition")
    q_words = set(re.split(r'[\s、。]+', query.lower()))
    keyword_match = sum(1 for w in q_words if len(w) >= 2 and w in response.lower())
    if keyword_match == 0 and len(q_words) >= 2: issues.append("no_keyword_match")
    template_phrases = ["一般的に", "例えば", "一方で", "また、", "つまり", "要するに"]
    if sum(1 for p in template_phrases if p in response) >= 3: issues.append("template_heavy")
    quality = 1.0
    if "empty_or_too_short" in issues: quality -= 0.5
    if "repetition" in issues: quality -= 0.4
    if "no_keyword_match" in issues: quality -= 0.2
    if "template_heavy" in issues: quality -= 0.2
    return max(0.0, quality), issues

def self_correct_response(messages: list, is_logic: bool, text_len: int, mode: str) -> str:
    global LEARNING_STATS
    if text_len < 20: return stream_response(messages, is_logic, text_len, temp_override=0.6, silent=True) or ""
    quality_threshold = 0.4
    temp_adjustments = ([0.15, 0.75] if not is_logic else [0.1, 0.5])[:2]
    query_str = messages[-1]["content"] if messages else ""
    for adj_temp in temp_adjustments:
        result = stream_response(messages, is_logic, text_len, temp_override=adj_temp, silent=True)
        if not result: continue
        quality, issues = self_evaluate_response(result, query_str)
        if quality >= quality_threshold: return result
        LEARNING_STATS["self_correction_count"] += 1
    return stream_response(messages, is_logic, text_len, temp_override=0.6, silent=True) or ""

def session_context_block() -> str:
    if not KEYWORD_MEMORY: return ""
    # 直近3件のみ注入。古い話題のキーワードがブリードしないよう絞る
    return f"\n【直近の話題】: {', '.join(KEYWORD_MEMORY[-3:])}\n"

def detect_hallucination(response: str) -> list[str]:
    if len(response) < 80: return []
    warnings = []
    def _is_known(text: str) -> bool:
        state = load_state()
        if any(text in e.get("term", "") or text in e.get("def", "") for e in state.get("dict", [])): return True
        if any(text in m.get("text", "") for m in state.get("memo", [])): return True
        if any(text in d.get("title", "") or text in d.get("text", "") for d in state.get("docs", [])): return True
        # s01_memory（会話記憶）を検索
        for vec_hit in vector_search(text, n=1):
            if text in vec_hit: return True
        # 書籍コレクションも検索
        for col in vector_list_collections():
            if col == "s01_memory": continue
            for vec_hit in vector_search(text, n=1, collection=col):
                if text in vec_hit: return True
        return False
    for m in re.finditer(r'[「『]([^」』]{2,50})[」』]', response):
        name = m.group(1).strip()
        if len(name) >= 3 and not _is_known(name): warnings.append(f"「{name}」は知識ベースに未登録（捏造の可能性）")
    for m in re.finditer(r'(?:『([^』]+)』|「([^」]+)」|(\S{2,20}))という(?:作品|曲|本|小説|漫画|アニメ|映画|ドラマ|番組|人|人物|場所|組織|会社|企業|国|都市|用語|言葉|考え方|制度|概念|現象|法則|理論|手法|技術|商品|製品|サービス|アプリ|ゲーム|キャラ|グループ|バンド|歌手|俳優|タレント|YouTuber|配信者|会社員|教授|博士|先生|作家|画家|監督|政治家|社長|理事長|代表取締役|フリーランス|デザイナー|エンジニア)', response):
        name = m.group(1) or m.group(2) or m.group(3)
        if name and len(name) >= 2 and not _is_known(name): warnings.append(f"「{name}」という未知のエンティティを提示")
    for m in re.finditer(r'([\u4E00-\u9FFF]{2,10}(?:は|が))(\d{3,}(?:年|月|日|人|個|件|社|店|億|万|千|百|％|パーセント|円|ドル|ユーロ|kg|g|km|m|cm|mm))', response):
        subject = m.group(1).rstrip("はが")
        if not _is_known(subject + m.group(2)[:6]): warnings.append(f"「{subject}」に関する数値主張「{m.group(2)}」— 未確認")
    for m in re.finditer(r'「([^」]{5,60})」と(?:言|述べ|語|話|コメント|発言)', response):
        if not _is_known(m.group(1)[:20]): warnings.append(f"引用文「{m.group(1)[:30]}...」— 出典不明")
    for m in re.finditer(r'([\u4E00-\u9FFF]{2,15})(?:は|が)(\d{3,4}年)(?:に|(?:に作|に公開|に出版|に発表|に発売|に設立|に開業|に開校|に開店|に開始|に終了|に完成))', response):
        if not _is_known(m.group(1) + m.group(2)): warnings.append(f"「{m.group(1)}」の「{m.group(2)}」— 未確認の年代")
    for m in re.finditer(r'([\u4E00-\u9FFF]{2,4})(?:教授|博士|先生|大臣|社長|会長|院長|学長|知事|市長|町長|村長|監督|選手|議員|長官|事務局長|理事長|代表|CEO|社長|部長|課長|係長|店長|所長|局長|管理官|参与|顧問|弁護士|会計士|税理士|医師|看護師|薬剤師|獣医師|教諭|准教授|講師|助教|助手|研究員|学芸員|司書|カウンセラー|セラピスト|トレーナー|コーチ|審判|解説者|アナウンサー)', response):
        if not _is_known(m.group(1)): warnings.append(f"「{m.group(1)}」— 肩書き付き人物だが未確認")
    for m in re.finditer(r'([\u30A1-\u30F4]{3,15})(?:とは|って|というのは|は、)(?:[\u4E00-\u9FFF]{2,}のこと|[\u4E00-\u9FFF]{2,}を指す|[\u4E00-\u9FFF]{2,}の一種)', response):
        if not _is_known(m.group(1)): warnings.append(f"「{m.group(1)}」— 定義説明があったが未確認の用語")
    return warnings

def _print_hallucination_warnings(response: str, strict: bool = False) -> None:
    """detect_hallucination の結果をターミナルに表示する。
    strict=True（/kb ask）のときは警告をより厳格に扱い、出力前に改行を入れる。"""
    warnings = detect_hallucination(response)
    if not warnings:
        return
    prefix = f"\n{C['y']}[ハルシネーション検出 {len(warnings)}件]{C['w']}"
    print(prefix)
    for w in warnings[:5]:   # 最大5件まで表示
        print(f"  {C['dim']}⚠ {w}{C['w']}")
    if strict and len(warnings) >= 3:
        print(f"  {C['r']}※ 局所参照外の情報が多く含まれる可能性。/kb search で原文を確認推奨。{C['w']}")

def detect_repetition(text: str, window: int = 150) -> bool:
    """繰り返し検出。"""
    if len(text) < window * 2: return False
    # バイナリ重複（完全一致）
    tail = text[-window * 2:]
    if tail[:len(tail)//2] == tail[len(tail)//2:]:
        return True
    # 同一比喩構文の多用（5回以上に緩和 — 3回だと豊かな散文も止まった）
    if len(re.findall(r'まるで.{5,50}(?:ようなもの|ような状況|ようだ|かのよう)', text)) >= 5:
        return True
    # 400字ウィンドウで前半=後半
    if len(text) >= 400:
        chunk = text[-400:]
        half = len(chunk) // 2
        if chunk[:half] == chunk[half:]:
            return True
    # 総文字数が4000字を超えたら強制終了（無制限生成の暴走防止）
    if len(text) > 4000:
        return True
    return False

def trim_history(ms: list, max_pairs: int = MAX_HISTORY) -> list:
    return ms[-(max_pairs * 2):] if len(ms) > max_pairs * 2 else ms

def build_chat_messages(sys_msg: dict, ms: list, persona: dict) -> list:
    fp = persona.get("first_person", "私")
    name = persona["name"]
    style_hint = persona["style"][:200]
    anchor = [
        {"role": "user", "content": "あなたのキャラクターを確認して。"},
        {"role": "assistant", "content": f"キャラ名は{name}。一人称は{fp}。{style_hint}。ずっとこのキャラで話し続けるよ。"},
    ]
    return [sys_msg] + anchor + trim_history(ms)

_cookie_jar = CookieJar()
_ctx = ssl.create_default_context()
_ctx.check_hostname = False
_ctx.verify_mode = ssl.CERT_NONE
_opener = R.build_opener(R.HTTPSHandler(context=_ctx), R.HTTPCookieProcessor(_cookie_jar))

