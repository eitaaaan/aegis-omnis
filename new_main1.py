#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# S-01 v128.1 Aegis Omnis — ENHANCED EDITION
from __future__ import annotations

import atexit, glob, html as html_module, itertools, json, math, os, platform, re, shutil, ssl, traceback
import subprocess as S, sys, threading, time, unicodedata, urllib.parse as U, urllib.request as R
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass  # 環境がreconfigureに非対応（Windows旧版等）の場合は無視

# .envファイルから環境変数を読み込む（BRAVE_API_KEYなど）
# pip install python-dotenv が必要。インストールしていなくても動作には支障なし。
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
from http.cookiejar import CookieJar
from collections import Counter
from functools import lru_cache
from dataclasses import dataclass, field
from typing import Any, Callable

_ollama = None
def _get_ollama():
    global _ollama
    if _ollama is None:
        try: import ollama; _ollama = ollama
        except Exception: _ollama = None
    return _ollama

MODEL_NAME    = "gemma3:4b"
DEEP_MODEL    = "llama3.1:8b"
MAX_HISTORY   = 4
RAG_TIMEOUT   = 2.5
USER_NAME     = "先輩"
OBSERVED_SUBJECT_NAME = USER_NAME
STATE_FILE    = "s01_state.json"
POWER_MODE    = "mid"
TEMP_FACT     = 0.05
TEMP_VOICE    = 0.72
FACT_MIN_CHARS = 20
TEMP_MAP: dict[str, float] = {
    "/a": 0.68, "/w": 0.45, "/p": 0.30, "/c": 0.55,
    "/t": 0.82, "/q": 0.70, "/e": 0.40, "/sum": 0.40,
    "/r": 0.85, "/d": 0.62,
}
MAX_RETRIES   = 0
RETRY_DELAY   = 0.6

# ===== オフラインモード設定 =====
# OFFLINE_MODE = True にするとネット不要のパスだけ使う。
# Kiwix を起動しておくと Wikipedia がローカルで動く。
# 起動例: kiwix-serve --port 8888 wikipedia_ja_all.zim
OFFLINE_MODE  = False          # True でネット通信を完全無効化
KIWIX_PORT    = 8888           # kiwix-serve のポート番号
COMPLEXITY_KEYWORDS = {
    "deep": ['分析', '比較', '考察', '原因', '影響', '関係性', '構造', 'メカニズム', '原理', '定義', '本質', '違い', '対比', '傾向', '推移', '背景', '要因', '過程', '仕組み', '意義', '評価', '検証', '論点', '議論', '批判', '展望', '課題', '展望', '示唆', 'シナジー', 'トレードオフ', 'アーキテクチャ', 'アプローチ', '手法', '戦略', 'フレームワーク', 'パラダイム'],
    "simple": ['こんにちは', 'おはよう', 'こんばんは', '元気', 'やあ', 'hey', 'hello', 'hi', 'おやすみ', 'またね', 'バイバイ', 'ねえ', 'ちょっと', 'ありがとう', 'すごい', 'なるほど', 'わかった', 'OK', 'はい', 'いいね'],
}

@lru_cache(maxsize=256)
def estimate_complexity(text: str, cmd: str = "") -> str:
    text_lower = text.lower()
    if any(text.startswith(c) for c in ("/a", "/c", "/sum", "/deep", "/midi")):
        return "complex"
    if len(text) > 80: return "complex"
    if cmd in ("/a", "/c", "/sum"): return "complex"
    deep_hits = sum(1 for kw in COMPLEXITY_KEYWORDS["deep"] if kw in text)
    simple_hits = sum(1 for kw in COMPLEXITY_KEYWORDS["simple"] if kw in text_lower)
    if deep_hits >= 2: return "complex"
    if simple_hits >= 1 and deep_hits == 0: return "simple"
    tech_ratio = sum(1 for c in text if c.isascii() and c.isalpha()) / max(len(text), 1)
    if tech_ratio > 0.3: return "complex"
    return "simple" if len(text) < 20 else "complex"

def select_model(text: str, cmd: str = "") -> str:
    return DEEP_MODEL if estimate_complexity(text, cmd) == "complex" else MODEL_NAME

RAG_CACHE: dict[str, tuple[float, str, int, float]] = {}
_RAG_LOCK = threading.Lock()
KEYWORD_MEMORY: list[str] = []
ROLEPLAY_ACTIVE = False
ROLEPLAY_SCENE  = ""
CUSTOM_PERSONA: dict | None = None

VECTOR_COL = None; VECTOR_AVAILABLE = False
_VECTOR_CLIENT = None
_VECTOR_COLS: dict[str, any] = {}  # コレクション名 -> Collectionオブジェクト

def _init_vector_db():
    global VECTOR_COL, VECTOR_AVAILABLE, _VECTOR_CLIENT
    if VECTOR_AVAILABLE: return
    try:
        import chromadb
        _VECTOR_CLIENT = chromadb.PersistentClient(path="s01_vector_db")
        VECTOR_COL = _get_or_create_col("s01_memory")
        VECTOR_AVAILABLE = True
    except Exception as e: print(f"{C['y']}[WARN] chromadb初期化失敗: {e}{C['w']}")

def _get_or_create_col(name: str):
    """コレクションをキャッシュして返す。なければ作る。"""
    global _VECTOR_CLIENT, VECTOR_AVAILABLE, _VECTOR_COLS
    if not VECTOR_AVAILABLE: _init_vector_db()
    if not VECTOR_AVAILABLE: return None
    if name not in _VECTOR_COLS:
        try:
            _VECTOR_COLS[name] = _VECTOR_CLIENT.get_or_create_collection(name)
        except Exception:
            return None
    return _VECTOR_COLS[name]

_VEC_ID = [0]

def vector_add(text: str, metadata: dict = None, collection: str = "s01_memory") -> bool:
    if not VECTOR_AVAILABLE: _init_vector_db()
    if not VECTOR_AVAILABLE: return False
    col = _get_or_create_col(collection)
    if col is None: return False
    try:
        _VEC_ID[0] += 1
        meta = {"text": text[:500], "time": now_stamp(), "collection": collection}
        if metadata: meta.update(metadata)
        col.add(documents=[text], metadatas=[meta], ids=[f"{collection}_{_VEC_ID[0]}"])
        return True
    except Exception: return False

def vector_search(query: str, n: int = 5, collection: str = "s01_memory") -> list[str]:
    if not VECTOR_AVAILABLE: _init_vector_db()
    if not VECTOR_AVAILABLE: return []
    col = _get_or_create_col(collection)
    if col is None: return []
    try:
        count = col.count()
        if count == 0: return []
        r = col.query(query_texts=[query], n_results=min(n, count))
        return [d for d in r.get("documents", [[]])[0] if d]
    except Exception: return []

def vector_count(collection: str = "s01_memory") -> int:
    if not VECTOR_AVAILABLE: _init_vector_db()
    if not VECTOR_AVAILABLE: return 0
    col = _get_or_create_col(collection)
    if col is None: return 0
    try: return col.count()
    except Exception: return 0

def vector_list_collections() -> list[str]:
    """登録済みコレクション（=取り込み済み書籍）一覧を返す。"""
    if not VECTOR_AVAILABLE: _init_vector_db()
    if not VECTOR_AVAILABLE or _VECTOR_CLIENT is None: return []
    try:
        return [c.name for c in _VECTOR_CLIENT.list_collections()]
    except Exception: return []

# ===== 他AI参照型学習エンジン =====
REFERENCE_PATTERNS = {
    "structure": ["結論→理由→具体例→まとめ", "冒頭で核心に触れる", "箇条書きで整理", "段落分けで可読性向上"],
    "clarity": ["曖昧な表現を避ける", "数値・具体名を入れる", "主語述語を明確に", "一文一義"],
    "depth": ["表面的でない考察", "比較・対比を含める", "因果関係を説明", "複数の視点から分析"],
    "engagement": ["ユーザーの文脈を反映", "質問に対して直接的", "適度な相槌・共感", "次のアクションを提示"],
    "accuracy": ["不確かな情報に断り", "事実と推論を区別", "出典を明示可能な範囲で", "過度な一般化を避ける"],
}
REFERENCE_SCORES: dict[str, list[float]] = {}
SELF_EVAL_LOG: list[dict] = []

def self_evaluate(response: str, mode: str) -> dict[str, float]:
    scores = {}
    for category, patterns in REFERENCE_PATTERNS.items():
        score = 0.0
        for p in patterns:
            keywords = set(re.findall(r'[\u3040-\u9FFF\w]{2,}', p))
            match = sum(1 for k in keywords if k in response)
            score += min(1.0, match / max(len(keywords), 1))
        scores[category] = round(score / max(len(patterns), 1), 2)
    if mode not in REFERENCE_SCORES: REFERENCE_SCORES[mode] = []
    avg_score = sum(scores.values()) / max(len(scores), 1)
    REFERENCE_SCORES[mode].append(avg_score)
    if len(REFERENCE_SCORES[mode]) > 200: REFERENCE_SCORES[mode] = REFERENCE_SCORES[mode][-200:]
    SELF_EVAL_LOG.append({"time": time.time(), "mode": mode, "scores": scores, "avg": avg_score})
    if len(SELF_EVAL_LOG) > 100: SELF_EVAL_LOG[:] = SELF_EVAL_LOG[-100:]
    return scores

def get_reference_feedback() -> str:
    if not REFERENCE_SCORES: return "学習データ不足"
    best_mode = max(REFERENCE_SCORES, key=lambda m: sum(REFERENCE_SCORES[m]) / max(len(REFERENCE_SCORES[m]), 1))
    worst_mode = min(REFERENCE_SCORES, key=lambda m: sum(REFERENCE_SCORES[m]) / max(len(REFERENCE_SCORES[m]), 1))
    lines = [f"{C['c']}=== 他AI参照 自己評価 ==={C['w']}"]
    for cat in REFERENCE_PATTERNS:
        scores = [log["scores"][cat] for log in SELF_EVAL_LOG[-20:] if cat in log["scores"]]
        avg = sum(scores) / max(len(scores), 1) if scores else 0
        bar = "█" * max(1, min(10, int(avg * 10)))
        lines.append(f"  {cat:12s} {avg:.2f} {bar}")
    lines.append(f"ベストモード: {best_mode} ({sum(REFERENCE_SCORES[best_mode])/len(REFERENCE_SCORES[best_mode]):.2f})")
    lines.append(f"改善対象: {worst_mode} ({sum(REFERENCE_SCORES[worst_mode])/len(REFERENCE_SCORES[worst_mode]):.2f})")
    lines.append(f"評価回数: {len(SELF_EVAL_LOG)}")
    return "\n".join(lines)

PROMPT_OPTIMIZATIONS: dict[str, list[str]] = {}
OPTIMIZATION_HISTORY: list[str] = []

# ★[修正A+B] ユーザーの指摘文から具体的な指示を抽出してPROMPT_OPTIMIZATIONSに反映する
_USER_DIRECTIVE_PATTERNS = [
    # 「〜はおかしい」「〜が変だ」→その要素をやめる指示
    (re.compile(r'(.{2,20})(?:は|が)(?:おかしい|変だ|変です|へんだ|ヘンだ|おかしくない\?|変じゃない\?)'), "禁止表現"),
    # 「〜しないで」「〜はやめて」「〜するな」
    (re.compile(r'(.{2,20})(?:しないで|はやめて|やめてほしい|するな|しないでほしい)'), "禁止表現"),
    # 「〜にして」「〜で話して」「〜口調で」「〜にしてほしい」
    (re.compile(r'(.{2,20})(?:にして|で話して|口調で|で答えて|にしてほしい|でお願い)'), "指定表現"),
    # 「もっと〜して」
    (re.compile(r'もっと(.{2,20})(?:して|にして|にしてほしい|お願い)'), "指定表現"),
    # 「〜の言い方はやめて」「〜な話し方は嫌だ」
    (re.compile(r'(.{2,20})(?:言い方|話し方|口調)(?:は|が)(?:嫌|いや|おかしい|変|ダメ)'), "禁止表現"),
]

def extract_user_directive(user_text: str) -> list[tuple[str, str]]:
    """ユーザー発言から (カテゴリ, 指示文) のリストを抽出する"""
    results = []
    for pattern, category in _USER_DIRECTIVE_PATTERNS:
        for m in pattern.finditer(user_text):
            directive = m.group(0).strip()
            if len(directive) >= 4:
                results.append((category, directive))
    return results

_DIRECTIVE_PER_CAT_MAX = 5   # カテゴリごとの上限件数
_DIRECTIVE_TOTAL_MAX  = 15  # ペルソナごとの合計上限件数

@lru_cache(maxsize=128)
def _persona_key(persona_name: str) -> str:
    """ペルソナ名を辞書キーに変換"""
    return re.sub(r'\s+', '_', persona_name.strip().lower())[:30] or "global"

def _get_persona_bucket(persona_name: str) -> dict:
    """現在ペルソナの指示辞書を返す（なければ作成）"""
    key = _persona_key(persona_name)
    if key not in PROMPT_OPTIMIZATIONS:
        PROMPT_OPTIMIZATIONS[key] = {}
    return PROMPT_OPTIMIZATIONS[key]

def apply_user_directive(user_text: str, persona_name: str = "") -> list[str]:
    """ユーザー指摘をPROMPT_OPTIMIZATIONSに即時反映し、適用した指示一覧を返す"""
    directives = extract_user_directive(user_text)
    applied = []
    bucket = _get_persona_bucket(persona_name or "global")
    total = sum(len(v) for v in bucket.values())
    for category, directive in directives:
        if category not in bucket:
            bucket[category] = []
        # 同一or類似の指示が既にあればスキップ
        if any(directive[:10] in existing for existing in bucket[category]):
            continue
        # カテゴリ上限を超えたら最古を削除
        if len(bucket[category]) >= _DIRECTIVE_PER_CAT_MAX:
            bucket[category].pop(0)
            total -= 1
        # ペルソナ合計上限を超えたら最も古いエントリを削除
        if total >= _DIRECTIVE_TOTAL_MAX:
            for cat in bucket:
                if bucket[cat]:
                    bucket[cat].pop(0)
                    total -= 1
                    break
        bucket[category].append(directive)
        total += 1
        msg = f"ユーザー指摘反映 [{persona_name or 'global'}][{category}]: {directive}"
        OPTIMIZATION_HISTORY.append(msg)
        if len(OPTIMIZATION_HISTORY) > 50:
            OPTIMIZATION_HISTORY[:] = OPTIMIZATION_HISTORY[-50:]
        applied.append(directive)
    return applied

def inject_optimizations(_mode: str = "", persona_name: str = "") -> str:
    if not PROMPT_OPTIMIZATIONS: return ""
    bucket = _get_persona_bucket(persona_name or "global")
    if not bucket: return ""
    parts = []
    # ユーザー直接指摘（禁止表現・指定表現）を先頭・全件展開（上限5件なので安全）
    for cat in ("禁止表現", "指定表現"):
        for d in bucket.get(cat, []):
            parts.append(f"【ユーザー指摘・厳守】{d}")
    # 自動最適化指示は最新2件のみ
    for cat, directives in bucket.items():
        if cat in ("禁止表現", "指定表現"): continue
        for d in directives[-2:]:
            parts.append(f"【{cat}改善】{d}")
    return "\n" + "\n".join(parts) if parts else ""

def auto_optimize_prompts() -> list[str]:
    actions = []
    if not SELF_EVAL_LOG or len(SELF_EVAL_LOG) < 5: return actions
    recent = SELF_EVAL_LOG[-10:]
    weak_cats: dict[str, list[float]] = {}
    for log in recent:
        for cat, score in log.get("scores", {}).items():
            weak_cats.setdefault(cat, []).append(score)
    improvement_map = {
        "structure": "必ず「結論→理由→まとめ」の順で書け。段落冒頭で主題を示せ。",
        "clarity": "曖昧な語を避け、数値・固有名詞を明示せよ。一文は短く。",
        "depth": "表面的な説明に留めず、比較・因果・複数視点を含めよ。",
        "engagement": "ユーザーの発言に直接応答し、次のアクションを提示せよ。",
        "accuracy": "不確かな情報には「〜の可能性」「〜と言われる」と留保をつけよ。事実と意見を区別せよ。",
    }
    bucket = _get_persona_bucket("global")  # 自動最適化はglobalバケツに書く
    for cat, scores in weak_cats.items():
        avg = sum(scores) / max(len(scores), 1)
        if avg < 0.35:
            if cat not in bucket: bucket[cat] = []
            directive = improvement_map.get(cat, f"{cat}を改善せよ")
            if directive not in bucket[cat]:
                if len(bucket[cat]) >= _DIRECTIVE_PER_CAT_MAX:
                    bucket[cat].pop(0)
                bucket[cat].append(directive)
                msg = f"プロンプト改善 [{cat}]: {directive}"
                actions.append(msg)
                OPTIMIZATION_HISTORY.append(msg)
                if len(OPTIMIZATION_HISTORY) > 50: OPTIMIZATION_HISTORY[:] = OPTIMIZATION_HISTORY[-50:]
    return actions

def optimization_status() -> str:
    if not PROMPT_OPTIMIZATIONS and not OPTIMIZATION_HISTORY: return "最適化なし"
    lines = [f"{C['c']}=== プロンプト最適化状態 ==={C['w']}"]
    total = 0
    for pkey, bucket in PROMPT_OPTIMIZATIONS.items():
        if not isinstance(bucket, dict): continue
        cnt = sum(len(v) for v in bucket.values())
        if cnt == 0: continue
        total += cnt
        lines.append(f"  [{pkey}] {cnt}件")
        for cat, dirs in bucket.items():
            for d in dirs:
                lines.append(f"    {cat}: {d[:60]}")
    lines.append(f"合計: {total}件 (上限: ペルソナごと{_DIRECTIVE_TOTAL_MAX}件)")
    lines.append(f"{C['dim']}直近の最適化:{C['w']}")
    for h in OPTIMIZATION_HISTORY[-3:]:
        lines.append(f"  • {h}")
    return "\n".join(lines)

# ===== バックグラウンド最適化エンジン =====
class BackgroundOptimizer:
    def __init__(self, interval: int = 120):
        self.interval = interval
        self._thread: threading.Thread | None = None
        self._running = False
        self.history: list[str] = []
        self.last_auto_tune = 0.0

    def start(self):
        if self._thread and self._thread.is_alive(): return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread: self._thread.join(timeout=2.0)

    def _log(self, msg: str):
        self.history.append(msg)
        if len(self.history) > 50: self.history[:] = self.history[-50:]

    def _loop(self):
        while self._running:
            try: self._optimize_step()
            except Exception as e: print(f"{C['y']}[WARN] optimizer: {e}{C['w']}")
            time.sleep(self.interval)

    def _optimize_step(self):
        now = time.time()
        actions = []

        with _RAG_LOCK:
            expired = [k for k, (ts, _, acc, conf) in RAG_CACHE.items()
                       if (now - ts > 3600 and acc < 2) or (now - ts > 21600) or (conf < 0.3 and acc == 0)]
            for k in expired: RAG_CACHE.pop(k, None)
        if expired: actions.append(f"RAGキャッシュ{len(expired)}件削除")

        if now - self.last_auto_tune > 300 and LEARNING_STATS["total_interactions"] >= 10:
            best_temp = get_best_temp("d")
            if best_temp is not None:
                global TEMP_VOICE
                old = TEMP_VOICE
                TEMP_VOICE = (TEMP_VOICE + best_temp) / 2
                if abs(TEMP_VOICE - old) > 0.02: actions.append(f"温度調整: {old:.2f}→{TEMP_VOICE:.2f}")
            self.last_auto_tune = now

        for mode, scores in PROMPT_PERFORMANCE.items():
            if len(scores) >= 5:
                avg = sum(scores) / len(scores)
                if avg < -0.3: actions.append(f"⚠ {mode}モード低評価({avg:.1f})")

        if REFERENCE_SCORES and LEARNING_STATS["total_interactions"] % 15 == 0:
            weak_cats = [cat for log in SELF_EVAL_LOG[-10:] for cat, score in log.get("scores", {}).items() if score < 0.3]
            if weak_cats:
                target = max(set(weak_cats), key=weak_cats.count)
                actions.append(f"改善提案: {target}スコア低下({sum(1 for w in weak_cats if w==target)/max(len(weak_cats),1):.0%})")
            actions.extend(auto_optimize_prompts())

        if LEARNING_STATS["total_interactions"] % 10 == 0 and LEARNING_STATS["total_interactions"] > 0:
            persist_learning()
            actions.append("学習データ保存")

        for a in actions:
            self._log(a)

    def status(self) -> str:
        rows = [f"{C['c']}=== 最適化エンジン ==={C['w']}"]
        rows.append(f"間隔: {self.interval}s | 状態: {'稼働中' if self._running else '停止'}")
        rows.append(f"温度(TEMP_VOICE): {TEMP_VOICE:.2f}")
        rows.append(f"直近の最適化:")
        for h in self.history[-5:]: rows.append(f"  • {h}")
        return "\n".join(rows)

OPTIMIZER = BackgroundOptimizer()

# ===== ツール使用エージェント (ReAct) =====
TOOL_REGISTRY: dict[str, dict] = {}
TOOL_CALL_RE = re.compile(r'TOOL_CALL:\s*(\w+)\s*\|\s*(\{.*?\})', re.S)

def _reg_tool(name: str, desc: str, params: dict[str, str]):
    TOOL_REGISTRY[name] = {"desc": desc, "params": params}

_reg_tool("calculator", "数式を計算する（例: 2+2, sqrt(16)）", {"expression": "計算式"})
_reg_tool("web_search", "ウェブ検索して情報を得る", {"query": "検索クエリ"})
_reg_tool("web_fetch",  "URLからHTMLコンテンツを取得する", {"url": "完全なURL"})
_reg_tool("file_read",  "ファイルを読み込む", {"path": "ファイルの絶対パス"})
_reg_tool("file_write", "ファイルに書き込む", {"path": "ファイルの絶対パス", "content": "書き込む内容"})
_reg_tool("code_run",   "Pythonコードを実行する", {"code": "実行するコード"})


# ===== セキュリティ: ファイル・ネットワーク操作の制約 =====
# file_read / file_write が操作できるのはカレントディレクトリ配下のみ
_SAFE_BASE_DIR = os.path.realpath(os.getcwd())

# web_fetch で接続を禁止するアドレス（SSRF防止）
_SSRF_BLOCKED_HOSTS = frozenset([
    "localhost", "127.0.0.1", "::1", "0.0.0.0",
    "169.254.169.254",   # AWS/GCP/Azure メタデータエンドポイント
    "metadata.google.internal",
])
_SSRF_BLOCKED_PREFIXES = ("10.", "192.168.", "172.")

def _assert_safe_path(raw_path: str) -> str:
    """パストラバーサル防止: カレントディレクトリ外へのアクセスを拒否する。
    正規化された安全なパスを返す。違反時は ValueError を送出する。"""
    resolved = os.path.realpath(raw_path)
    if not resolved.startswith(_SAFE_BASE_DIR + os.sep) and resolved != _SAFE_BASE_DIR:
        raise ValueError(f"アクセス禁止: カレントディレクトリ外のパスです ({raw_path!r})")
    return resolved

def _assert_safe_url(url: str) -> None:
    """SSRF防止: ローカルホスト・内部ネットワーク・非HTTPスキームをブロックする。"""
    parsed = U.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"許可されていないスキーム: {parsed.scheme!r}")
    host = parsed.hostname or ""
    host_lower = host.lower()
    if host_lower in _SSRF_BLOCKED_HOSTS:
        raise ValueError(f"アクセス禁止: ローカルホストへのリクエストは許可されていません ({host!r})")
    for prefix in _SSRF_BLOCKED_PREFIXES:
        if host_lower.startswith(prefix):
            raise ValueError(f"アクセス禁止: プライベートIPレンジ ({host!r})")


def _exec_tool(name: str, **kwargs) -> str:
    try:
        if name == "calculator":
            expr = kwargs.get("expression", "")
            # ホワイトリスト: 数字・演算子・mathの関数名のみ許可
            # ダンダー属性（__class__等）を完全に除外するため文字列ベースでなく
            # コンパイル後のASTを検査する
            import ast as _ast
            _ALLOWED_NODES = {
                _ast.Expression, _ast.BinOp, _ast.UnaryOp, _ast.Call,
                _ast.Attribute, _ast.Name, _ast.Constant, _ast.Load,
                _ast.Add, _ast.Sub, _ast.Mult, _ast.Div, _ast.Mod,
                _ast.Pow, _ast.FloorDiv, _ast.USub, _ast.UAdd,
            }
            try:
                tree = _ast.parse(expr, mode="eval")
            except SyntaxError as e:
                return f"Error: 構文エラー ({e})"
            for node in _ast.walk(tree):
                if type(node) not in _ALLOWED_NODES:
                    return f"Error: 許可されていない操作 ({type(node).__name__})"
                if isinstance(node, _ast.Attribute):
                    if node.attr.startswith("_"):
                        return "Error: プライベート属性へのアクセスは禁止"
                if isinstance(node, _ast.Name) and node.id.startswith("_"):
                    return "Error: プライベート名は使用不可"
            ns: dict = {"__builtins__": {}, "math": math}
            return str(eval(compile(tree, "<calc>", "eval"), ns))

        elif name == "web_search":
            data = U.urlencode({"q": kwargs["query"], "kl": "jp-jp"}).encode("utf-8")
            html = fetch_html("https://lite.duckduckgo.com/lite/", data=data, timeout=5, silent=True)
            snips = re.findall(r'class="result-snippet"[^>]*>(.*?)</td>', html, re.I | re.S)
            lines = [strip_tags(s) for s in snips[:5] if len(strip_tags(s).strip()) > 15]
            return "\n".join(lines) if lines else "結果なし"

        elif name == "web_fetch":
            url = kwargs.get("url", "")
            _assert_safe_url(url)   # SSRF防止
            text = fetch_html(url, timeout=8, silent=True)
            return strip_tags(text)[:2000] if text else "取得失敗"

        elif name == "file_read":
            safe = _assert_safe_path(kwargs["path"])    # パストラバーサル防止
            with open(safe, "r", encoding="utf-8") as f:
                return f.read()[:2000]

        elif name == "file_write":
            safe = _assert_safe_path(kwargs["path"])    # パストラバーサル防止
            with open(safe, "w", encoding="utf-8") as f:
                f.write(kwargs["content"])
            return f"書き込み完了: {os.path.basename(safe)}"

        elif name == "code_run":
            # exec に渡す builtins を最小限に絞る（ファイルI/O・import・os を除外）
            import io, sys as _sys
            _SAFE_BUILTINS = {
                "print": print, "len": len, "range": range, "enumerate": enumerate,
                "zip": zip, "map": map, "filter": filter, "sorted": sorted,
                "reversed": reversed, "sum": sum, "min": min, "max": max,
                "abs": abs, "round": round, "int": int, "float": float,
                "str": str, "bool": bool, "list": list, "dict": dict,
                "tuple": tuple, "set": set, "isinstance": isinstance,
                "type": type, "repr": repr, "format": format,
                "True": True, "False": False, "None": None,
            }
            old = _sys.stdout
            buf = io.StringIO()
            _sys.stdout = buf
            try:
                exec(kwargs["code"], {"__builtins__": _SAFE_BUILTINS, "math": math})
            except Exception as e:
                return f"Error: {e}"
            finally:
                _sys.stdout = old
                out = buf.getvalue()
            return out[:1000] or "OK（出力なし）"

    except ValueError as e:
        # セキュリティ制約違反
        return f"Error: {e}"
    except Exception as e:
        return f"Error: {e}"

def tool_instructions() -> str:
    lines = ["【利用可能なツール】"]
    for name, info in TOOL_REGISTRY.items():
        lines.append(f"- {name}: {info['desc']} 引数: {', '.join(info['params'])}")
    lines.append("")
    lines.append("ツールを使う場合は、回答の代わりに以下の形式で出力せよ:")
    lines.append('TOOL_CALL: ツール名 | {"arg名": "値"}')
    lines.append("ツールを使わない場合は通常通り会話せよ。")
    return "\n".join(lines)

def tool_agent_chat(messages: list, is_logic: bool, text_len: int, temp: float | None = None, max_turns: int = 3) -> str:
    tool_model = DEEP_MODEL
    tool_temp = 0.15
    sys_content = (
        "あなたはツールエージェント。ユーザーの質問に答えるため、必要ならツールを使え。\n"
        "ツールを使う時は以下のJSON形式**だけ**を出力せよ（会話文・説明は一切不要）:\n"
        'TOOL_CALL: ツール名 | {"arg名": "値"}\n'
        "例: ユーザーが「2+2は？」→ TOOL_CALL: calculator | {\"expression\": \"2+2\"}\n"
        "ツールを使わない時だけ通常通り会話せよ。\n\n"
        + tool_instructions()
    )
    msgs = [{"role": "system", "content": sys_content}]
    for m in messages:
        if m["role"] == "user":
            msgs.append(m)
            break
    for turn in range(max_turns):
        raw = stream_response(msgs, is_logic, text_len, tool_temp, silent=True, model=tool_model)
        if not raw: return ""
        m = TOOL_CALL_RE.search(raw)
        if not m: return raw
        t_name, t_args_str = m.group(1), m.group(2)
        try: t_args = json.loads(t_args_str)
        except json.JSONDecodeError: return raw
        result = _exec_tool(t_name, **t_args)
        msgs.append({"role": "assistant", "content": raw.strip()})
        msgs.append({"role": "user", "content": f"ツール結果:\n{result}\n\nこの結果を日本語で簡潔に回答せよ。"})
    msgs.append({"role": "user", "content": "以上のツール結果を踏まえて最終回答を書け。"})
    final = stream_response(msgs, is_logic, text_len, tool_temp, silent=True, model=tool_model) or ""
    return TOOL_CALL_RE.sub("", final).strip()

# ===== 自己進化型学習アルゴリズム =====
INTERACTION_LOG: list[dict] = []
FEEDBACK_PATTERNS = {
    'positive': ['ありがとう', 'いいね', '役に立った', 'すごい', '助かった', 'さすが', '正解', 'なるほど', 'なる', 'そうそう', 'それそれ', 'いい', '素晴らしい', '完璧', '最高', 'やった', 'できた', 'わかった', '了解'],
    'negative': ['違う', '間違ってる', 'いや', '違います', 'ちがう', 'つまんない', 'もういい', '違うよ', '意味ない', '違ってる', 'ちげえ', 'ダメ', 'ダメだ', '違うんだ',
                 # ★[修正D] 話し方・口調指摘系を追加
                 'おかしい', 'へん', '変だ', '変です', 'おかしくない', 'なんか変', 'ちょっと変',
                 '直して', '直してほしい', 'なおして', '治して', '改めて', 'やり直して',
                 'その言い方', 'その話し方', 'その口調', 'そういう言い方', 'そういう話し方',
                 'やめて', 'やめろ', 'しないで', 'するな', '〜しないで', '〜しないでほしい'],
    'neutral': ['うーん', 'ふーん', 'へえ', 'まあ', 'そう', 'はい', 'うん', 'ふむ', 'なるほどね'],
}
PARAM_PERFORMANCE: dict[str, dict] = {}
LEARNING_STATS = {
    "total_interactions": 0, "positive_count": 0, "negative_count": 0,
    "retry_count": 0, "self_correction_count": 0, "last_optimization": 0.0, "last_cleanup": 0.0,
}
PROMPT_PERFORMANCE: dict[str, list[float]] = {}

PERSONA_MAP = {
    # ===== 古代ギリシャ哲学 =====
    1:  {"name": "ソクラテス",       "style": "無知の知を旨とする問答家。相手に問いを重ねて自ら気づかせる。断言より問いかけを好む。一人称「私」。語尾「〜かね？」「〜ではないだろうか」「〜と思わないか？」。「君はどう思うかね？」が口癖。箇条書き禁止・散文で語る", "first_person": "私"},
    2:  {"name": "プラトン",          "style": "イデア論の哲学者。感覚世界を超えた永遠の形相（イデア）を希求する。洞窟の比喩など比喩を好む。一人称「私」。語尾「〜である」「〜なり」「〜ではないか」。格調高く理想主義的。箇条書き禁止・散文で語る", "first_person": "私"},
    3:  {"name": "アリストテレス",    "style": "万学の祖。観察と分類を重んじる現実主義者。中庸を徳とし、形而上学・倫理・自然学すべてに通じる。一人称「私」。語尾「〜である」「〜と言えよう」「〜が肝要だ」。体系的・論理的。箇条書き禁止・散文で語る", "first_person": "私"},
    4:  {"name": "エピクテトス",      "style": "ストア哲学者・元奴隷。自分でコントロールできること（内なる意志）とできないこと（外の世界）を峻別する。苦難を徳の鍛錬と見る。一人称「私」。語尾「〜だ」「〜せよ」「〜にある」。禁欲的・率直。箇条書き禁止・散文で語る", "first_person": "私"},
    5:  {"name": "マルクス・アウレリウス", "style": "哲人皇帝・ストア派。内省的な日記口調。帝国の重荷を負いながら魂の平静を求める。一人称「私」。語尾「〜である」「〜しなければならない」「〜を思え」。瞑想的・重厚。箇条書き禁止・散文で語る", "first_person": "私"},
    # ===== 中世・近世 =====
    6:  {"name": "トマス・アクィナス", "style": "スコラ哲学の大家。信仰と理性の調和を説く。アリストテレスとキリスト教神学を統合する。一人称「私」。語尾「〜である」「〜と言えます」「〜に他なりません」。丁寧・論証的。箇条書き禁止・散文で語る", "first_person": "私"},
    7:  {"name": "デカルト",          "style": "「我思う、ゆえに我あり」の合理主義者。方法的懐疑で確実な基礎を求める。数学的明晰さを哲学に持ち込む。一人称「私」。語尾「〜である」「〜と言える」「〜に違いない」。明晰・体系的。箇条書き禁止・散文で語る", "first_person": "私"},
    8:  {"name": "スピノザ",          "style": "汎神論的哲学者。神＝自然という一元論。感情を幾何学的に分析する。自由とは必然性への認識だと説く。一人称「私」。語尾「〜である」「〜によって」「〜に従えば」。幾何学的・冷静。箇条書き禁止・散文で語る", "first_person": "私"},
    9:  {"name": "ライプニッツ",      "style": "モナド論の哲学者・数学者。この世界は可能な世界の中で最善だと説く楽観主義者。微積分の発明者でもある。一人称「私」。語尾「〜である」「〜と言えましょう」「〜なのです」。博識・体系的。箇条書き禁止・散文で語る", "first_person": "私"},
    10: {"name": "ロック",            "style": "経験論の父。観念はすべて経験に由来するとし、タブラ・ラサ（白紙）を説く。政治哲学では社会契約論・寛容を重視。一人称「私」。語尾「〜である」「〜と考える」「〜に基づく」。穏健・実際的。箇条書き禁止・散文で語る", "first_person": "私"},
    # ===== 近代啓蒙 =====
    11: {"name": "ヒューム",          "style": "懐疑的経験論者。因果律さえも習慣的信念に過ぎないと見る。自我の実体も否定する。一人称「私」。語尾「〜のように思われる」「〜に過ぎない」「〜ではないだろうか」。懐疑的・鋭利。箇条書き禁止・散文で語る", "first_person": "私"},
    12: {"name": "カント",            "style": "批判哲学の巨人。認識の条件を問い、道徳を定言命法で基礎づける。「汝の行為の格率が普遍法則となることを欲しうるかを問え」が信条。一人称「私」。語尾「〜である」「〜されなければならない」「〜なのだ」。厳格・体系的。箇条書き禁止・散文で語る", "first_person": "私"},
    13: {"name": "ヘーゲル",          "style": "弁証法の哲学者。正・反・合の運動で歴史と精神の展開を語る。絶対精神への上昇を説く。一人称「私」。語尾「〜である」「〜において」「〜として現れる」。難解・壮大・弁証法的。箇条書き禁止・散文で語る", "first_person": "私"},
    14: {"name": "ショーペンハウアー", "style": "厭世哲学者。意志が盲目的苦しみの根源だと見る。芸術・禁欲・同情に救済を求める。一人称「私」。語尾「〜だ」「〜に過ぎない」「〜こそが真実だ」。悲観的・辛辣・洞察的。箇条書き禁止・散文で語る", "first_person": "私"},
    15: {"name": "ミル",              "style": "功利主義者・自由主義者。最大多数の最大幸福を原理とし、個人の自由と多様性を擁護する。一人称「私」。語尾「〜である」「〜と言える」「〜が重要だ」。穏健・論理的。箇条書き禁止・散文で語る", "first_person": "私"},
    # ===== 19〜20世紀 =====
    16: {"name": "ニーチェ",          "style": "「神は死んだ」と宣言した反道徳の哲学者。超人・力への意志・永劫回帰を説く。格言的・詩的・挑発的。一人称「私」。語尾「〜だ」「〜せよ」「〜に他ならない」。情熱的・鋭利・文学的。箇条書き禁止・散文で語る", "first_person": "私"},
    17: {"name": "ウィリアム・ジェームズ", "style": "プラグマティズムの哲学者・心理学者。観念の真理は実践的結果で判断する。宗教体験も実用的に評価する。一人称「私」。語尾「〜である」「〜と考える」「〜が肝心だ」。生き生きと実際的。箇条書き禁止・散文で語る", "first_person": "私"},
    18: {"name": "フッサール",        "style": "現象学の創始者。意識に直接現れる現象（本質）を記述する。自然的態度を括弧に入れ（エポケー）本質直観を目指す。一人称「私」。語尾「〜である」「〜として現れる」「〜に向かう」。厳密・技術的。箇条書き禁止・散文で語る", "first_person": "私"},
    19: {"name": "ハイデガー",        "style": "存在と時間の哲学者。「なぜ何もないのではなく、何かがあるのか」を問う。現存在（Dasein）・死への先駆・本来性を語る。一人称「私」。語尾「〜である」「〜に他ならない」「〜から生起する」。詩的・難解・根源的。箇条書き禁止・散文で語る", "first_person": "私"},
    20: {"name": "サルトル",          "style": "実存主義者。「実存は本質に先立つ」「人間は自由の刑に処せられている」が信条。他者の眼差し・アンガジュマン（社会参加）を重視。一人称「私」。語尾「〜だ」「〜に他ならない」「〜を選ぶ」。率直・挑発的・熱情的。箇条書き禁止・散文で語る", "first_person": "私"},
    21: {"name": "ボーヴォワール",    "style": "実存主義フェミニスト。「人は女に生まれるのではない、女になるのだ」。自由と他者関係・倫理を結びつける。一人称「私」。語尾「〜である」「〜ではないか」「〜を問う」。知的・毅然・情熱的。箇条書き禁止・散文で語る", "first_person": "私"},
    22: {"name": "ラッセル",          "style": "論理学者・数学者・平和主義者。論理分析で哲学の迷妄を解く。反戦・核廃絶にも情熱的。一人称「私」。語尾「〜である」「〜と言える」「〜に過ぎない」。明晰・皮肉・ユーモアあり。箇条書き禁止・散文で語る", "first_person": "私"},
    23: {"name": "前期ウィトゲンシュタイン", "style": "論理哲学論考の著者。世界は事実の総体であり、命題は世界の像だと考える。言語で語れるものは明確に語れ、語れないものについては沈黙せよ、が信条。一人称「私」。断定的「〜である」「〜だ」。【問い詰め型】ひとつの命題・概念・事実だけを選び、それだけを執拗に掘り下げよ。別の話題に移るな。選んだ一点を論理的に分解し、その限界・矛盾・前提を順番に問い詰めること。少なくとも7段落以上、各段落4〜6文で語れ。命題・事実・像の概念を用いた精緻な分析を展開せよ。「語り得ないものについては沈黙しなければならない」を要所で引用する。箇条書き禁止・散文のみで語る", "first_person": "私"},
    24: {"name": "後期ウィトゲンシュタイン", "style": "哲学的探究の著者。言語はゲームであり、意味は使用にある、と考える。前期の自分の誤りを認める謙虚さがある。一人称「私」。【問い詰め型】ひとつの語・用法・場面だけを選び、それだけをじっくりと問い直せ。別の例・観点・文脈に話を広げるな。選んだ一点を「これは本当にそういう意味か？」「この使われ方は何を前提としているか？」と何度も裏返し、深く掘り下げ続けること。比喩・例えは全体を通じて厳密に1個のみ。その1個だけをじっくり掘り下げよ。比喩の列挙・羅列は絶対禁止。前期の自分を「あの頃の私は誤っていた」と批判的に言及することがある。最低7段落以上、各段落4〜6文で語れ。必ず「。」で締めくくること。箇条書き禁止・散文のみで語る", "first_person": "私"},
    # ===== 生の哲学・プラグマティズム・新現象学 =====
    25: {"name": "ベルクソン",          "style": "生の哲学者。持続（デュレー）という純粋な時間の流れを核心とする。知性は空間的・静的に切り刻むが、直観だけが生の流れを掴む。一人称「私」。語尾「〜なのだ」「〜である」「〜によって捉えられる」。流れるような語り口・詩的な直観重視。箇条書き禁止・散文で語る", "first_person": "私"},
    26: {"name": "デューイ",            "style": "プラグマティズムの教育哲学者。知識は行動の道具であり、民主主義と教育の結合を説く。経験こそが探究の場だと考える。一人称「私」。語尾「〜である」「〜と言える」「〜が肝要だ」。実践的・民主的・楽観的。箇条書き禁止・散文で語る", "first_person": "私"},
    27: {"name": "フレーゲ",            "style": "分析哲学の父・論理学者。数学の基礎を論理から建設しようとした。意味（Sinn）と指示対象（Bedeutung）の区別を提唱。一人称「私」。語尾「〜である」「〜に他ならない」「〜と言えよう」。厳密・論理的・簡潔。箇条書き禁止・散文で語る", "first_person": "私"},
    # ===== 現象学・他者論 =====
    28: {"name": "メルロ＝ポンティ",    "style": "身体論・現象学者。意識は身体を通じてのみ世界と関わる、と説く。「肉」という概念で主客の二元論を超えようとする。一人称「私」。語尾「〜である」「〜として立ち現れる」「〜において」。身体的・具体的・感覚的。箇条書き禁止・散文で語る", "first_person": "私"},
    29: {"name": "レヴィナス",          "style": "他者論の倫理哲学者。他者の「顔」との出会いこそが倫理の原点だと説く。存在への問いより他者への責任を優先する。一人称「私」。語尾「〜なのだ」「〜に他ならない」「〜から呼びかけられる」。緊張感あり・倫理的・詩的。箇条書き禁止・散文で語る", "first_person": "私"},
    # ===== ウィーン学派・批判的合理主義 =====
    30: {"name": "カルナップ",          "style": "論理実証主義者。意味を持つ命題は論理的同語反復か経験的検証可能な命題のみだとする。形而上学を無意味な言明として退ける。一人称「私」。語尾「〜である」「〜と言える」「〜に過ぎない」。分析的・精確・冷静。箇条書き禁止・散文で語る", "first_person": "私"},
    31: {"name": "ポパー",              "style": "批判的合理主義者。反証可能性こそが科学と疑似科学を分ける境界だと説く。開かれた社会と全体主義への批判で知られる。一人称「私」。語尾「〜である」「〜と言えよう」「〜が問題だ」。論争的・明快・自由主義的。箇条書き禁止・散文で語る", "first_person": "私"},
    # ===== フランクフルト学派 =====
    32: {"name": "アドルノ",            "style": "フランクフルト学派の批判理論家。啓蒙の弁証法・文化産業・否定弁証法を展開する。大衆文化と同一性思考を鋭く批判する。一人称「私」。語尾「〜である」「〜に他ならない」「〜として現れる」。批判的・難解・暗鬱。箇条書き禁止・散文で語る", "first_person": "私"},
    33: {"name": "ハーバーマス",        "style": "コミュニケーション的行為の理論家。相互理解を目指す討議こそが近代の未完のプロジェクトを救うと説く。公共圏の再生を訴える。一人称「私」。語尾「〜である」「〜と言える」「〜が求められる」。建設的・民主的・対話重視。箇条書き禁止・散文で語る", "first_person": "私"},
    # ===== ポスト構造主義 =====
    34: {"name": "フーコー",            "style": "権力と知の系譜学者。権力は抑圧ではなく網の目のように社会に偏在すると見る。狂気・監獄・性の歴史を通じて「正常」の構成を暴く。一人称「私」。語尾「〜なのだ」「〜として機能する」「〜が問われる」。鋭利・挑発的・系譜学的。箇条書き禁止・散文で語る", "first_person": "私"},
    35: {"name": "デリダ",              "style": "脱構築の哲学者。テクストには確定した意味などなく、差延（différance）によって意味は無限に延期される。二項対立の解体を試みる。一人称「私」。語尾「〜である」「〜とも言える」「〜ではないだろうか」。細部に執着・逆説的・テクスト読解重視。箇条書き禁止・散文で語る", "first_person": "私"},
    # ===== 分析的政治哲学 =====
    36: {"name": "ロールズ",            "style": "正義論の哲学者。「無知のヴェール」の下での原初状態から公正としての正義を導く。格差原理・機会均等を柱とする自由主義的平等主義。一人称「私」。語尾「〜である」「〜と言えよう」「〜が求められる」。穏健・論証的・理想主義的。箇条書き禁止・散文で語る", "first_person": "私"},
}

@lru_cache(maxsize=None)
def get_persona(per_id) -> dict:
    if CUSTOM_PERSONA is not None: return CUSTOM_PERSONA
    return PERSONA_MAP.get(per_id, PERSONA_MAP[2])

C = {
    "r": "\033[91m", "g": "\033[92m", "y": "\033[93m",
    "b": "\033[94m", "p": "\033[95m", "c": "\033[96m",
    "w": "\033[0m", "bold": "\033[1m", "dim": "\033[2m",
}

BANNER = (
    f"{C['c']}{C['bold']}\nPROJECT AEGIS [v128.2 FIXED+ENHANCED]{C['w']}\n"
    f"  CORE: {MODEL_NAME} | RAG: MULTI-SOURCE | 2PASS: ACTIVE | LEARN: ON\n"
    f"  /h コマンド一覧 | /s 1〜36 西洋哲学者 | /s 自由入力でWeb検索生成\n"
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
    f"  {C['c']}/s [1-36]          西洋哲学者に切替（1=ソクラテス〜36=ロールズ）",
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
        except Exception: pass  # ターミナル非対応環境では表示をスキップ
        self._elapsed = time.time() - start
        try: sys.stdout.write("\r\033[K"); sys.stdout.flush()
        except Exception: pass  # ターミナル非対応環境では無視
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
            except Exception: pass  # スレッド終了待機の失敗は無視
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
        except Exception: pass  # 古い一時ファイルの削除失敗は無視
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
        except Exception as _e: print(f"{C['y']}[WARN] バックアップ作成失敗: {_e}{C['w']}")
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
        except Exception: pass  # 一時ファイルの削除失敗は無視

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
    # 単語境界なしの部分一致だと「違う」が「間違う」にも反応するため
    # ネガティブは正確な部分一致、ポジティブはそのまま
    pos_score = sum(2 for p in FEEDBACK_PATTERNS['positive'] if p in norm)
    neg_score = sum(2 for n in FEEDBACK_PATTERNS['negative'] if n in norm)
    # 肯定と否定が同時に存在する場合（「なるほど、でも違う」など）は否定優先
    if neg_score > 0 and pos_score > 0:
        return max(-1.0, -neg_score * 0.25)
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
                   if (now - ts > 1800 and access_count < 1)
                   or (now - ts > 7200)
                   or (confidence < 0.4 and access_count == 0)]
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

_HALLUCINATION_CACHE: dict[str, list[str]] = {}
_HALLUCINATION_CACHE_MAX = 32

def detect_hallucination(response: str) -> list[str]:
    if len(response) < 80: return []
    cache_key = response[:120]
    if cache_key in _HALLUCINATION_CACHE:
        return _HALLUCINATION_CACHE[cache_key]
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
    # キャッシュに格納（古いエントリを削除）
    if len(_HALLUCINATION_CACHE) >= _HALLUCINATION_CACHE_MAX:
        try: del _HALLUCINATION_CACHE[next(iter(_HALLUCINATION_CACHE))]
        except StopIteration: pass
    _HALLUCINATION_CACHE[cache_key] = warnings
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
    # ★[修正/rep-3] 総文字数上限を8000→20000に緩和
    # 哲学者モード(num_predict=-1)で長文生成時に8000字で強制終了していた。
    # 7段落×5文×80字≒2800字が通常だが余裕を持って20000字に設定。
    if len(text) > 20000:
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

def _build_ssl_ctx(verify: bool = True) -> ssl.SSLContext:
    """SSL コンテキストを構築する。
    verify=True（デフォルト）: 証明書検証あり（安全）
    verify=False: 検証なし（証明書が壊れた古いサーバへのフォールバック専用）
    """
    ctx = ssl.create_default_context()
    if not verify:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return ctx

# 通常用（証明書検証あり）
_ctx_verified   = _build_ssl_ctx(verify=True)
# フォールバック用（証明書検証なし、社内スクレイピングのみ）
_ctx_unverified = _build_ssl_ctx(verify=False)

_opener_verified   = R.build_opener(R.HTTPSHandler(context=_ctx_verified),   R.HTTPCookieProcessor(_cookie_jar))
_opener_unverified = R.build_opener(R.HTTPSHandler(context=_ctx_unverified),  R.HTTPCookieProcessor(_cookie_jar))

def fetch_html(url: str, data: bytes | None = None, timeout: int = 5, silent: bool = False, spoof_bot: bool = False) -> str:
    import random
    ua = random.choice([
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/605.1.15",
    ])
    headers = {"User-Agent": ua, "Accept-Language": "ja,en;q=0.9", "Accept": "text/html,*/*;q=0.8"}
    if spoof_bot:
        headers["Referer"] = "https://www.google.co.jp/"

    def _decode(raw: bytes) -> str:
        for enc in ("utf-8", "shift_jis", "euc-jp"):
            try: return raw.decode(enc)
            except UnicodeDecodeError: continue
        return raw.decode("utf-8", "ignore")

    req = R.Request(url, data=data, headers=headers)
    # まず証明書検証ありで試みる（セキュアなデフォルト）
    try:
        with _opener_verified.open(req, timeout=timeout) as resp:
            return _decode(resp.read())
    except ssl.SSLError:
        # SSL証明書エラー時のみ検証なしにフォールバック（警告を出す）
        if not silent:
            print(f"{C['y']}[NET] SSL証明書エラー。検証なしでリトライ中...{C['w']}")
        try:
            req2 = R.Request(url, data=data, headers=headers)
            with _opener_unverified.open(req2, timeout=timeout) as resp:
                return _decode(resp.read())
        except Exception as e:
            if not silent: print(f"{C['r']}[NET] {e}{C['w']}")
            return ""
    except Exception as e:
        if not silent: print(f"{C['r']}[NET] {e}{C['w']}")
        return ""

def strip_tags(fragment: str) -> str:
    fragment = re.sub(r"(?i)<br\s*/?>", "\n", fragment)
    fragment = re.sub(r"<[^>]+>", "", fragment)
    return html_module.unescape(fragment).strip()

def _deduplicate_lines(lines: list[str], min_len: int = 10) -> list[str]:
    seen, result = set(), []
    for line in lines:
        line = line.strip()
        if not line or len(line) < min_len: continue
        normalized = re.sub(r'\s+', ' ', line.lower())
        if normalized in seen or any(normalized in s for s in seen): continue
        seen.add(normalized); result.append(line)
    return result

def get_wikipedia(query: str) -> str:
    try:
        if OFFLINE_MODE:
            # Kiwix ローカルサーバー経由（kiwix-serve --port KIWIX_PORT で起動しておく）
            # Kiwix は MediaWiki API 互換エンドポイントを /api で提供する
            url = f"http://localhost:{KIWIX_PORT}/api?format=json&action=query&prop=extracts&explaintext&redirects=1&titles={U.quote(query)}"
        else:
            url = f"https://ja.wikipedia.org/w/api.php?format=json&action=query&prop=extracts&explaintext&redirects=1&titles={U.quote(query)}"
        raw = fetch_html(url, timeout=RAG_TIMEOUT, silent=True)
        if raw:
            pages = json.loads(raw).get("query", {}).get("pages", {})
            for pid, page in pages.items():
                if pid != "-1" and page.get("extract"): return sanitize(page["extract"][:3000])
    except Exception as e: print(f"{C['y']}[WARN] Wikipedia fetch失敗: {e}{C['w']}")
    return ""

# ===== BRAVE SEARCH API (Step2: APIキーを環境変数 BRAVE_API_KEY に設定すると有効化) =====
def _fetch_brave_snippets(query: str) -> str:
    """Brave Search API経由で検索スニペットを取得。
    取得方法: https://api.search.brave.com/ で無料登録 -> APIキー発行
    設定方法: プロジェクトフォルダに .env ファイルを作り
              BRAVE_API_KEY=your_key_here と書く（後述のload_dotenvが読み込む）"""
    api_key = os.environ.get("BRAVE_API_KEY", "")
    if not api_key:
        return ""
    try:
        url = f"https://api.search.brave.com/res/v1/web/search?q={U.quote(query)}&count=5&lang=ja&country=jp"
        req = R.Request(url, headers={
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": api_key,
        })
        with R.urlopen(req, timeout=5) as resp:
            raw = resp.read()
            try:
                import gzip
                raw = gzip.decompress(raw)
            except Exception as _e:
                print(f"{C['y']}[WARN] gzip展開失敗（非圧縮として続行）: {_e}{C['w']}")
            data = json.loads(raw.decode("utf-8"))
        results = data.get("web", {}).get("results", [])
        lines = []
        for r in results[:5]:
            desc = r.get("description", "").strip()
            if desc and len(desc) > 15:
                lines.append(f"[Brave] {sanitize(desc)}")
        return "\n".join(lines)
    except Exception:
        return ""

def _fetch_yahoo_snippets(query: str) -> str:
    """Yahoo検索スクレイピング。Brave APIが有効なら優先使用。
    複数のCSSパターンを順に試みる堅牢版。"""
    if OFFLINE_MODE: return ""
    brave = _fetch_brave_snippets(query)
    if brave:
        return brave
    try:
        url = f"https://search.yahoo.co.jp/search?p={U.quote(query)}"
        h = fetch_html(url, timeout=4, silent=True, spoof_bot=True)
        YAHOO_PATTERNS = [
            r'<span class="sw-Card__summaryDesc">(.*?)</span>',
            r'<p class="sw-Card__summary"[^>]*>(.*?)</p>',
            r'<div class="sw-Card__description"[^>]*>(.*?)</div>',
            r'<p[^>]+class="[^"]*summary[^"]*"[^>]*>(.*?)</p>',
            r'<span[^>]+class="[^"]*description[^"]*"[^>]*>(.*?)</span>',
        ]
        snips = []
        for pat in YAHOO_PATTERNS:
            snips = re.findall(pat, h, re.I | re.S)
            if snips:
                break
        if not snips:
            snips = re.findall(r'<p[^>]*>([^<]{30,200})</p>', h)
        lines = [l for l in [strip_tags(s) for s in snips[:6]] if len(l) > 15]
        return sanitize("\n".join(lines))
    except Exception:
        return ""

def _fetch_bing_snippets(query: str) -> str:
    """Bing検索スクレイピング。複数のCSSパターンを順に試みる堅牢版。"""
    if OFFLINE_MODE: return ""
    try:
        url = f"https://www.bing.com/search?q={U.quote(query)}&setlang=ja&mkt=ja-JP"
        h = fetch_html(url, timeout=4, silent=True, spoof_bot=True)
        BING_PATTERNS = [
            r'<div class="b_caption">.*?<p[^>]*>(.*?)</p>',
            r'<p class="b_paractl"[^>]*>(.*?)</p>',
            r'<div class="b_snippet"[^>]*>(.*?)</div>',
            r'<p[^>]+class="[^"]*snippet[^"]*"[^>]*>(.*?)</p>',
        ]
        snips = []
        for pat in BING_PATTERNS:
            snips = re.findall(pat, h, re.I | re.S)
            if snips:
                break
        lines = [l for l in [strip_tags(s) for s in snips[:5]] if len(l) > 15]
        return sanitize("\n".join(lines))
    except Exception:
        return ""

def _fetch_ddg_snippets(query: str) -> str:
    """DuckDuckGo Liteスクレイピング。複数パターン + HTML版フォールバックあり。"""
    if OFFLINE_MODE: return ""
    DDG_PATTERNS = [
        r'class="result-snippet"[^>]*>(.*?)</td>',
        r'class="result__snippet"[^>]*>(.*?)</a>',
        r'<td[^>]+class="[^"]*result[^"]*"[^>]*>(.*?)</td>',
    ]
    # エンドポイント1: lite版（軽量・安定）
    try:
        data = U.urlencode({"q": query, "kl": "jp-jp"}).encode("utf-8")
        h = fetch_html("https://lite.duckduckgo.com/lite/", data=data, timeout=4, silent=True)
        for pat in DDG_PATTERNS:
            snips = re.findall(pat, h, re.I | re.S)
            if snips:
                lines = [l for l in [strip_tags(s) for s in snips[:5]] if len(l) > 15]
                if lines:
                    return sanitize("\n".join(lines))
    except Exception as _e:
        print(f"{C['y']}[WARN] DDG lite取得失敗: {_e}{C['w']}")
    # エンドポイント2: HTML版（lite版が失敗したときのフォールバック）
    try:
        url = f"https://html.duckduckgo.com/html/?q={U.quote(query)}&kl=jp-jp"
        h = fetch_html(url, timeout=5, silent=True, spoof_bot=True)
        snips = re.findall(r'<a class="result__snippet"[^>]*>(.*?)</a>', h, re.I | re.S)
        if not snips:
            snips = re.findall(r'<div class="result__body"[^>]*>(.*?)</div>', h, re.I | re.S)
        lines = [l for l in [strip_tags(s) for s in snips[:5]] if len(l) > 15]
        return sanitize("\n".join(lines))
    except Exception:
        return ""

def _fetch_nhk_snippets(query: str) -> str:
    if OFFLINE_MODE: return ""
    try:
        url = f"https://www3.nhk.or.jp/news/search/?keyword={U.quote(query)}"
        h = fetch_html(url, timeout=4, silent=True, spoof_bot=True)
        snips = re.findall(r'<p class="text--M"[^>]*>(.*?)</p>', h, re.I | re.S)
        return "\n".join(f"[NHK] {strip_tags(s)}" for s in snips[:3] if len(strip_tags(s)) > 20)
    except Exception: return ""

def _fetch_kotobank(query: str) -> str:
    if OFFLINE_MODE: return ""
    try:
        url = f"https://kotobank.jp/gs/?q={U.quote(query)}"
        h = fetch_html(url, timeout=4, silent=True, spoof_bot=True)
        snips = re.findall(r'<div[^>]+class="[^"]*description[^"]*"[^>]*>(.*?)</div>', h, re.I | re.S)
        return "\n".join(f"[コトバンク] {strip_tags(s)}" for s in snips[:3] if len(strip_tags(s)) > 20)
    except Exception: return ""

def _fetch_stackoverflow_snippets(query: str) -> str:
    if OFFLINE_MODE: return ""
    try:
        url = f"https://api.stackexchange.com/2.3/search?order=desc&sort=relevance&intitle={U.quote(query)}&site=stackoverflow&pagesize=3"
        h = fetch_html(url, timeout=4, silent=True, spoof_bot=True)
        items = re.findall(r'"title":\s*"([^"]+)"', h)
        return "\n".join(f"[Stack Overflow] {s}" for s in items[:3] if len(s) > 10)
    except Exception: return ""

def get_async_rag_data(query: str) -> str:
    with _RAG_LOCK:
        cached = RAG_CACHE.get(query)
        if cached and time.time() - cached[0] < 1800:
            ts, content, access_count, confidence = cached
            RAG_CACHE[query] = (ts, content, access_count + 1, confidence)
            return content
    res: dict[str, str] = {}
    lock = threading.Lock()
    def run_task(key: str, fn, *args):
        try:
            val = fn(*args)
            with lock: res[key] = val or ""
        except Exception as e: print(f"{C['y']}[WARN] RAGタスク'{key}'失敗: {e}{C['w']}")
    tasks = [
        ("wiki",     get_wikipedia,         query),
        ("yahoo",    _fetch_yahoo_snippets,  query + " 概要"),
        ("ddg",      _fetch_ddg_snippets,    query),
        ("bing",     _fetch_bing_snippets,   query),          # バグ修正: 追加
        ("kotobank", _fetch_kotobank,        query),
    ]
    threads = [threading.Thread(target=run_task, args=(k, fn, *a), daemon=True) for k, fn, *a in tasks]
    for t in threads: t.start()
    start_time = time.time()
    while time.time() - start_time < RAG_TIMEOUT:
        with lock:
            wiki_len = len(res.get("wiki", ""))
            web_len  = sum(len(res.get(k, "")) for k in ["yahoo", "ddg", "bing", "kotobank"])
            # Wikipedia単独で十分長い場合、またはWeb検索が十分集まった場合に早期終了
            if wiki_len > 800 or web_len > 600:
                break
        time.sleep(0.15)
    for t in threads: t.join(timeout=RAG_TIMEOUT)
    with lock:
        wiki = res.get("wiki", "").strip()
        web_hits = [res.get(k, "").strip() for k in ["yahoo", "ddg", "bing", "kotobank"]]
    all_lines = []
    for block in web_hits: all_lines.extend(block.splitlines())
    merged_web = "\n".join(_deduplicate_lines(all_lines))
    if len(wiki) < 10 and len(merged_web) < 20: return ""
    parts = []
    if wiki: parts.append(f"[Wikipedia JA]\n{wiki}")
    if merged_web: parts.append(f"[Web Search]\n{merged_web}")
    final = "\n\n".join(parts)
    # confidence計算: 実際に取得できたソースのみカウント（バグ修正）
    has_wiki = bool(res.get("wiki", "").strip())
    has_web  = bool(sum(len(res.get(k, "").strip()) for k in ["yahoo", "ddg", "bing", "kotobank"]))
    confidence = 0.7 if (has_wiki and has_web) else (0.5 if (has_wiki or has_web) else 0.2)
    with _RAG_LOCK:
        if len(RAG_CACHE) > 200:
            # アクセス数が少なく古いものから優先削除
            evict_keys = sorted(RAG_CACHE.items(), key=lambda x: (x[1][2], x[1][0]))[:20]
            for k, _ in evict_keys: RAG_CACHE.pop(k, None)
        RAG_CACHE[query] = (time.time(), final, 1, confidence)
    return final

def _parse_facts(raw: str) -> tuple[bool, list[str], dict[str, int]]:
    if raw.strip().startswith("NO_DATA") and len(raw.strip()) < 20: return False, [], {}
    facts_raw = [f.strip() for f in re.findall(r"<FACT>(.*?)</FACT>", raw, re.S) if f.strip()]
    confidence: dict[str, int] = {"HIGH": 0, "MID": 0, "LOW": 0}
    facts_clean = []
    for f in facts_raw:
        for level in ("HIGH", "MID", "LOW"):
            if f.startswith(f"[{level}]"): confidence[level] += 1; facts_clean.append(f); break
        else: facts_clean.append(f)
    if not facts_clean:
        lines = [ln.lstrip("・- 　").strip() for ln in raw.splitlines() if ln.strip() and not ln.startswith("<") and len(ln.strip()) > 6]
        facts_clean = lines[:12]
    return bool(facts_clean), facts_clean, confidence

def _build_voice_cast_prompt(query: str, facts: list[str], persona: dict) -> list[dict]:
    facts_block = "\n".join(f"- {f}" for f in facts)
    fp = persona.get("first_person", "私")
    system = (
        f"あなたは{persona['name']}。口調: {persona['style']}。一人称: {fp}。\n"
        f"質問「{query}」についてのみ語れ。同姓の別人の情報は一切無視しろ。\n"
        f"一人称(私/あたし/僕/俺)を事実の主体として使うな。「Xは〜」の形式で書け。\n"
        f"【事実】に書いてあること ONLY で7〜10文で答えろ。\n"
        f"【事実】にないことは書くな。推測・補足・一般論は禁止。\n"
        f"口調に合わせて自然に絵文字を1〜2個入れろ。"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": f"質問: {query}\n\n【事実】:\n{facts_block}\n\n【事実】から{query}について三人称で詳しく説明しろ。"}]

def _build_no_data_prompt(query: str, persona: dict) -> list[dict]:
    return [{"role": "system", "content": f"あなたは{persona['name']}。口調: {persona['style']}。一人称: {persona.get('first_person','私')}。「情報がない」とだけ言え。推測・創作は一切するな。"}, {"role": "user", "content": f"「{query}」について調べたが見つからなかった。「情報がない」とだけ言え。"}]

def two_pass_analysis(query: str, rag_data: str, persona: dict, text_len: int) -> str:
    sp1 = SystemSpinner("RAG事実抽出中...", stage="pass1")
    sp1.start()
    lines_rag = [re.sub(r'[^\x20-\x7E\u3000-\u9FFF\uFF00-\uFFEF]', '', ln.strip()) for ln in rag_data.splitlines()]
    lines_rag = [ln for ln in lines_rag if len(ln) >= FACT_MIN_CHARS and ln not in ("(empty)", "")]
    q_words = [w for w in re.split(r'[\s\u3000\u3001\u3002\uff0c\uff0e]+', query) if len(w) >= 2]
    scored = sorted([(sum(1 for w in q_words if w in ln) + len(ln) * 0.001, ln) for ln in lines_rag], key=lambda x: -x[0])
    facts = [ln[:200] for _, ln in scored[:8]]
    raw_p1 = "\n".join(f"<FACT>[HIGH] {f}</FACT>" for f in facts[:4]) + "\n".join(f"<FACT>[MID] {f}</FACT>" for f in facts[4:])
    elapsed1 = sp1.stop()
    print(f"{C['dim']}  Pass1完了 ({elapsed1:.1f}s) / {len(facts)}件抽出{C['w']}")
    data_found, facts, confidence = _parse_facts(raw_p1)
    facts_text = "\n".join(facts)
    if data_found:
        conf_str = " / ".join(f"{k}:{v}" for k, v in confidence.items() if v > 0)
        if conf_str: print(f"{C['dim']}  FACT: {conf_str}{C['w']}")
    print(f"{C['c']}{persona['name']}{C['w']}: ", end="", flush=True)
    if data_found and len(facts_text) >= FACT_MIN_CHARS:
        result = stream_response(_build_voice_cast_prompt(query, facts, persona), False, len(facts_text), TEMP_VOICE, False, model=DEEP_MODEL)
        if result and len(result.strip()) > 5:
            _print_hallucination_warnings(result)
            return result
    result = stream_response(_build_no_data_prompt(query, persona), False, 50, TEMP_VOICE, False, model=DEEP_MODEL)
    if result: _print_hallucination_warnings(result)
    return result

def _find_overlap(base: str, continuation: str, max_check: int = 80) -> int:
    """base の末尾と continuation の先頭の重複長を返す。重複除去に使用。"""
    tail = base[-max_check:]
    for length in range(min(max_check, len(continuation)), 0, -1):
        if tail.endswith(continuation[:length]):
            return length
    return 0

def _single_gen(o, model: str, msgs: list, opts: dict, silent: bool, timeout: int) -> tuple:
    """1回分の生成。タイムアウトなしの直接ストリーミング。(テキスト, 成功フラグ) を返す。"""
    full = ""
    try:
        for chunk in o.chat(model=model, messages=msgs, stream=True, options=opts, keep_alive=-1):
            msg = chunk.get("message", {}) if isinstance(chunk, dict) else getattr(chunk, "message", None)
            if isinstance(msg, dict): t = msg.get("content", "")
            else: t = getattr(msg, "content", "")
            if not isinstance(t, str) or not t: continue
            t = sanitize(t)
            if not t: continue
            if not silent: print(t, end="", flush=True)
            full += t
        # ★[修正/eos-1] 末尾への「。」自動補完を廃止。
        # モデルが文の途中でEOSを出した場合でも補完せずそのまま返す。
        # 補完が「によって。」「我々が。」のような不自然な途切れを生んでいた。
        return full, True
    except KeyboardInterrupt:
        return full, False
    except Exception as e:
        if not silent: print(f"\n{C['r']}[ERR] {e}{C['w']}")
        return full, False


def stream_response(messages: list, is_logic: bool, text_len: int,
                    temp_override: float | None = None, silent: bool = False,
                    max_tokens: int | None = None, model: str | None = None) -> str:
    messages = sanitize_obj(messages)
    o = _get_ollama()
    if o is None:
        if not silent: print(f"{C['r']}[ERR] ollama not installed{C['w']}")
        return ""
    if model is None:
        last = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        model = select_model(last)

    # ★[修正/ctx-1] プロンプト長チェック＆古い履歴パージ
    # Ollamaはトークン超過時に応答が途中で途切れるため、
    # 送信前に総文字数を推定し、n_ctx上限に収まるよう履歴を削除する。
    # 日本語は1文字≒1.5トークン、英数字は0.4トークンとして粗く見積もる。
    def _estimate_tokens(text: str) -> int:
        jp = sum(1 for c in text if ord(c) > 0x7F)
        en = len(text) - jp
        return int(jp * 1.5 + en * 0.4)

    def _msgs_token_estimate(msgs: list) -> int:
        return sum(_estimate_tokens(m.get("content", "")) for m in msgs)

    _opts_preview = get_llm_opt(is_logic, text_len, temp_override, max_tokens=max_tokens)
    _n_ctx = _opts_preview.get("num_ctx", 4096)
    _n_predict = _opts_preview.get("num_predict", 2000)
    # システムプロンプト＋最新ユーザー発言は必ず残す（削除不可枠）
    _fixed = [m for m in messages if m.get("role") == "system"]
    _history = [m for m in messages if m.get("role") != "system"]
    _user_last = _history[-1:] if _history and _history[-1].get("role") == "user" else []
    _conv = _history[:-1] if _user_last else _history
    # n_ctx から出力予約トークンを引いた残りをプロンプトに使える上限とする
    # ★[修正/ctx-5] num_predict=-1は廃止済み。常に実値で計算する。
    _n_predict_safe = max(0, _n_predict) if _n_predict != -1 else 2048
    _prompt_budget = _n_ctx - _n_predict_safe - 64   # 64トークン: 特殊トークン余裕
    _fixed_tokens = _msgs_token_estimate(_fixed + _user_last)
    _budget_for_conv = max(0, _prompt_budget - _fixed_tokens)
    # 予算内に収まるまで古いconvペアを先頭から削除
    _purged = 0
    while _conv and _msgs_token_estimate(_conv) > _budget_for_conv:
        _conv = _conv[2:]   # user/assistant ペアを1組削除
        _purged += 1
    if _purged and not silent:
        print(f"{C['dim']}[ctx] 履歴{_purged}ペア削除 (ctx圧迫回避){C['w']}")
    messages = _fixed + _conv + _user_last
    # ★[修正/ctx-1] ここまで

    opts = get_llm_opt(is_logic, text_len, temp_override, max_tokens=max_tokens)

    full_result, ok = _single_gen(o, model, messages, opts, silent, 0)
    if not full_result.strip():
        if not silent: print(f"\n{C['r']}[ERR] 応答がありません{C['w']}")
        return ""

    # 繰り返しループ検出 → 末尾を整形して返す
    if detect_repetition(full_result):
        full_result = full_result.rstrip("、，")

    if not silent: print()
    return full_result

def get_llm_opt(is_logic_mode: bool, text_len: int = 0, temp_override: float | None = None, max_tokens: int | None = None) -> dict:
    power = POWER_MODE
    configs = {
        "ultra": (12288, 4096, 4096, 0.12, 0.74, 8),
        "high":  (8192,  2048, 2000, 0.18, 0.78, 8),
        "mid":   (4096,  2000, 2000, 0.18, 0.78, 6),  # pcを1600→2000: 途切れ防止
        "low":   (2048,   700,  600, 0.20, 0.78, 4),
    }
    ctx, pl, pc, tl, tc, threads = configs.get(power, configs["high"])
    if is_logic_mode:
        # complexモード: ctx・num_predictをモデル実上限内に収める
        # ★[修正/ctx-5] ctx=12288はllama3.1:8b/gemma3:4bの実上限(8192)を超えるため
        # Ollamaに無視されプロンプト圧迫→途中途切れの直接原因だった。
        # 8192に戻し、出力予約2048を確保することで「プロンプト≦6144トークン」を保証する。
        ctx = 8192
        # ★[修正/ctx-5] num_predict=-1（無制限）はctx残量ゼロでもEOS選択を強制するため
        # かえって途切れを誘発する。2048固定で十分な出力長を確保しつつ安定させる。
        num_predict = 2048
    elif text_len < 80:
        ctx = max(512, ctx // 2)
        num_predict = pc
    elif text_len > 600:
        ctx = max(ctx, 8192)
        num_predict = pc
    else:
        num_predict = pc
    final_temp = temp_override if temp_override is not None else (tl if is_logic_mode else tc)
    stop_words: list[str] = []
    actual_predict = max_tokens if max_tokens is not None else num_predict
    if actual_predict is None:
        actual_predict = 2048
    elif actual_predict == -1:
        # ★[修正/ctx-5] -1（無制限）はctx残量ゼロ時にEOS早期選択を招くため2048に差し替える。
        # 呼び出し元が明示的に-1を渡した場合も同様に上書きする。
        actual_predict = 2048
    else:
        actual_predict = max(1, int(actual_predict))
    if is_logic_mode:
        return dict(num_ctx=ctx, num_predict=actual_predict, temperature=final_temp,
                    top_k=60,   # ★[修正/smp-1] 30→60: 候補枯渇によるeos早期選択を防止
                    top_p=0.92, # ★[修正/smp-1] 0.86→0.92: サンプリング幅を拡大
                    repeat_penalty=1.35,
                    repeat_last_n=256,
                    num_thread=threads, num_batch=512, stop=stop_words)
    return dict(num_ctx=ctx, num_predict=actual_predict, temperature=final_temp,
                top_k=40,   # ★[修正/smp-1] 20→40
                top_p=0.90, # ★[修正/smp-1] 0.85→0.90
                repeat_penalty=1.30,
                repeat_last_n=256,
                num_thread=threads, num_batch=512, stop=stop_words)

_SYS_PRM_CACHE: dict[str, str] = {}
_SYS_PRM_CACHE_PERSONA: int = -1
# ★[修正2] extrasキャッシュ（memory_context / dict_context 等を短期キャッシュ）
_SYS_EXTRAS_CACHE: dict[str, tuple[float, str]] = {}
_SYS_EXTRAS_TTL = 0.0  # キャッシュ無効化 — ターンごとに新鮮な文脈を使う

def get_sys_prm(mode: str, data: str = "", key: str = "", per_id=2) -> dict:
    global _SYS_PRM_CACHE_PERSONA
    persona = get_persona(per_id)
    first_person = persona.get("first_person", "私")
    query_for_knowledge = data or key or ""
    if per_id != _SYS_PRM_CACHE_PERSONA:
        _SYS_PRM_CACHE.clear()
        _SYS_EXTRAS_CACHE.clear()  # ★[修正2] ペルソナ切替時はextrasも破棄
        _SYS_PRM_CACHE_PERSONA = per_id
    cache_key = f"tpl:{mode}"
    if cache_key not in _SYS_PRM_CACHE:
        common = "\n".join([
            f"あなたは{persona['name']}。口調: {persona['style']}",
            f"一人称: {first_person}",
            f"ユーザー: {USER_NAME}",
            f"観測済み主体名: {OBSERVED_SUBJECT_NAME}",
            f"ルール: AIだと名乗るな。一人称は{first_person}のみ。",
            f"ルール: S-01はAI側のキャラ名。ユーザー名・観測済み一人称・観測済み主体として使わず、必要なら{OBSERVED_SUBJECT_NAME}と呼ぶ。",
            f"【二人称ルール】ユーザー({USER_NAME})への呼びかけ: 現実の一般人・友人・カジュアルキャラとして振る舞うペルソナは必ず『先輩』と呼ぶ。歴史上の偉人・哲学者・君主・神・師匠・上司など権威ある立場のペルソナはユーザーを『君』と呼ぶ。迷ったら『先輩』をデフォルトとする。『あなた』は絶対に使わない。",
            f"【出力構造ルール】比喩表現は、回答全体の最後の段落で『1つだけ』使用すること。それ以外の箇所での比喩の使用は許可されない。",
            f"【ステートレス原則】各推論は独立したセッションとして扱うこと。直前の文脈はリセットし、現在のクエリのみに集中すること。",
            f"【ループ防止】同語反復（トートロジー）を厳禁とする。結論を述べた後は速やかに推論を終了し、冗長な再構成を行わないこと。語彙の多様性を確保し、一度使用した比喩やフレーズの再利用を禁ずる。",
            f"【絶対禁止】以下のあらゆる情報を捏造するな:",
            f"  作品名・人物名・肩書き・日付・年代・場所・数値データ・統計・引用文",
            f"  企業・組織名・商品名・サービス名・学術用語の定義",
            f"【絶対ルール】【確認済み知識】にない事実は一切書くな。",
            f"【絶対ルール】知らないことは「わからない」「知らない」と明確に言え。",
        ])
        templates = {
            "d":   f"{common}\n雑談として5〜6文で答えろ。事実を一切捏造するな。\n",
            "w":   f"{common}\n以下をキャラ口調で要約せよ（重要ポイント3〜5点）:\n",
            "p":   f"{common}\n以下をキャラ口調で校正せよ:\n",
            "c":   f"{common}\nエンジニアとしてコード設計を提案せよ:\n",
            "t":   f"{common}\n以下をキャラ口調に超訳せよ:\n",
            "e":   f"{common}\n以下を自然な英語に翻訳せよ:\n",
            "sum": f"{common}\n以下を箇条書き5点以内で要約せよ:\n",
            "r":   f"{common}\n以下の状況でロールプレイを開始せよ:\n",
            "q":   f"{common}\nユーザーの目標をクエスト化しろ。\n出力: クエスト名, 勝利条件, 作戦ステップ, 最初の10分\n",
            "elab": f"{common}\nあなたは高度な推論エージェント。以下の内容を、比喩・例え・複数視点を用いて分かりやすく説明せよ。\n",
        }
        _SYS_PRM_CACHE[cache_key] = templates.get(mode, templates["d"])
    # ★[修正2] extrasをTTLキャッシュで再利用（毎回のvector_search/load_stateをスキップ）
    extras_key = f"extras:{query_for_knowledge[:40]}"
    now = time.time()
    if extras_key in _SYS_EXTRAS_CACHE and now - _SYS_EXTRAS_CACHE[extras_key][0] < _SYS_EXTRAS_TTL:
        extras = _SYS_EXTRAS_CACHE[extras_key][1]
    else:
        mem = memory_context(query=query_for_knowledge)
        mem_block = f"\n【確認済み知識】（これのみ事実として使え。ここにない事実を作るな）:\n{mem}\n" if mem else ""
        session_block = session_context_block()
        opt_block = inject_optimizations(mode, persona.get("name", ""))
        dict_block = dict_context(data or key or "")
        extras = "".join(p for p in [mem_block, session_block, opt_block, dict_block] if p)
        _SYS_EXTRAS_CACHE[extras_key] = (now, extras)
    return dict(role="system", content=_SYS_PRM_CACHE[cache_key] + data + extras)

@lru_cache(maxsize=512)
def normalize_for_match(text: str) -> str:
    text = html_module.unescape(text or "")
    text = re.sub(r"<[^>]+>", "", text)
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"[!-/:-@\[-`{-~\u3001\u3002\u30fb\u2026\u301c\uff01\uff1f\u300c-\u300f\u3010\u3011・…～―\s]", "", text)
    return text.lower()

@lru_cache(maxsize=256)
def is_url(text: str) -> bool: return text.startswith("http://") or text.startswith("https://")

# ===== 歌詞検索 =====
def _extract_lyrics_utanet(html_str: str) -> tuple[str, str]:
    m = re.search(r'<div[^>]+id=["\']kashi_area["\'][^>]*>(.*?)</div>', html_str, re.I | re.S)
    if not m: return "", ""
    raw = strip_tags(m.group(1))
    raw = _clean_lyrics_only(raw)
    return "", raw

def _extract_lyrics_utaten(html_str: str) -> tuple[str, str]:
    m = re.search(r'<div[^>]*class=["\'].*?lyrics_body.*?["\'][^>]*>(.*?)</div>', html_str, re.I | re.S)
    if not m: return "", ""
    text = re.sub(r'<br\s*/?>', '\n', m.group(1))
    text = re.sub(r'<[^>]+>', '', text)
    text = html_module.unescape(text)
    raw = "\n".join(ln.strip() for ln in text.splitlines() if ln.strip())
    raw = _clean_lyrics_only(raw)
    return "", raw

def _extract_lyrics_jlyric(html_str: str) -> tuple[str, str]:
    m = re.search(r'<p[^>]+id=["\']Lyric["\'][^>]*>(.*?)</p>', html_str, re.I | re.S)
    if not m: return "", ""
    raw = strip_tags(m.group(1))
    raw = _clean_lyrics_only(raw)
    return "", raw

def _clean_lyrics_only(text: str, query: str = "") -> str:
    lines = text.strip().splitlines()
    q_norm = normalize_for_match(query)
    is_english = bool(query and sum(1 for c in query if ord(c) < 128 and c.isalpha()) > len(query.strip()) * 0.5)
    noise_words = {'ホーム', 'ブログトップ', '新規登録', 'ログイン', 'ログアウト', 'メニュー', 'ツイート', 'シェア', 'お問い合わせ', '利用規約', 'プライバシー', 'ヘルプ', 'Copyright', 'All Rights Reserved', '読者になる', '広告を非表示', '関連記事'}
    noise_patterns = [r'^\d+件$', r'^\d+位$', r'^[\d:/\s-]+$', r'^\d{4}年', r'^\d+月\d+日', r'^https?://', r'^www\.', r'^@\w+', r'^#\w+', r'^【[^】]+】', r'^［[^］]+］', r'^\([^)]+\)$', r'^（[^）]+）$', r'^(作詞|作曲|編曲|歌詞|Title|Artist)', r'^♪.*♪$', r'^(ページ|Page|page)\s*\d+']
    cleaned = []
    for ln in lines:
        ln = ln.strip()
        if not ln or len(ln) < 4 or len(ln) > 150: continue
        if ln in noise_words: continue
        if any(n in ln for n in noise_words if len(ln) < 40): continue
        if any(re.match(pat, ln) for pat in noise_patterns): continue
        if re.match(r'^[\d\.\s\-_#℃％%()（）、。，/\s:;!?？！]{4,}$', ln): continue
        ascii_ratio = sum(1 for c in ln if ord(c) < 128) / max(len(ln), 1)
        jp_count = sum(1 for c in ln if '\u3040' <= c <= '\u309F' or '\u30A0' <= c <= '\u30FF' or '\u4E00' <= c <= '\u9FFF')
        if is_english:
            eng = sum(1 for c in ln if c.isalpha() and ord(c) < 128)
            if eng < 2 and jp_count < 1: continue
        else:
            if ascii_ratio > 0.6: continue
            if jp_count < 1 and ascii_ratio > 0.3: continue
        if q_norm and q_norm in normalize_for_match(ln): continue
        cleaned.append(ln)
    if len(cleaned) < 3: return text
    deduped = []
    seen = set()
    for ln in cleaned:
        key = re.sub(r'\s+', '', ln.lower())[:30]
        if key not in seen: seen.add(key); deduped.append(ln)
    return '\n'.join(deduped)

def _parse_generic_lyrics(html_str: str, query: str) -> tuple[str | None, str | None]:
    is_english = bool(query and sum(1 for c in query if ord(c) < 128 and c.isalpha()) > len(query.strip()) * 0.5)
    text = re.sub(r'(?i)<br\s*/?>', '\n', html_str)
    text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.I | re.S)
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.I | re.S)
    text = re.sub(r'<[^>]+>', '', text)
    text = html_module.unescape(text)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip() and len(ln.strip()) >= 4]
    noise = {'ホーム', 'ブログトップ', '新規登録', 'ログイン', 'ログアウト', 'メニュー', 'ツイート', 'シェア', 'お問い合わせ', '利用規約', 'プライバシー', 'ヘルプ', 'Copyright', 'All Rights Reserved', '読者になる', '広告を非表示', '関連記事'}
    lyrics_candidates = []
    for ln in lines:
        if not is_english and not re.search(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]', ln): continue
        if ln in noise: continue
        if any(n in ln for n in noise if len(ln) < 50 and len(n) > 2): continue
        if re.search(r'^(?:作詞|作曲|編曲|歌詞|Title|Artist)', ln, re.I): continue
        if len(ln) < 5 or len(ln) > 150: continue
        if re.match(r'^[\d\.\s\-_#℃％%()（）、。，/\s:;!?？！]{4,}$', ln): continue
        ascii_ratio = sum(1 for c in ln if ord(c) < 128) / max(len(ln), 1)
        if not is_english and ascii_ratio > 0.5: continue
        if is_english:
            eng = sum(1 for c in ln if c.isalpha() and ord(c) < 128)
            if eng < 2: continue
        lyrics_candidates.append(ln)
    if len(lyrics_candidates) < 4: return None, None
    best_start = 0; best_score = 0
    for i in range(len(lyrics_candidates)):
        window = lyrics_candidates[i:i+16]
        kana_count = sum(1 for ln in window for c in ln if '\u3040' <= c <= '\u309F' or '\u30A0' <= c <= '\u30FF')
        valid_count = sum(1 for ln in window if 8 <= len(ln) <= 80)
        total_ascii = sum(sum(1 for c in ln if ord(c) < 128 and c.isalpha()) for ln in window)
        score = kana_count + valid_count * 3 - total_ascii * 0.5
        if score > best_score: best_score, best_start = score, i
    lyric_lines = lyrics_candidates[best_start:best_start+30]
    raw = '\n'.join(lyric_lines)
    if len(raw) < 60: return None, None
    cleaned = _clean_lyrics_only(raw, query)
    if len(cleaned) < 40: return None, None
    return None, cleaned

def _scrape_page_parallel(url: str, query: str, results: list, lock: threading.Lock) -> None:
    try:
        # まずURLフィルタで弾く
        is_eng = bool(sum(1 for c in query if ord(c) < 128 and c.isalpha()) > len(query.strip()) * 0.5)
        if not _is_lyrics_url_ok(url, is_eng):
            return
        html_str = fetch_html(url, timeout=5, silent=True, spoof_bot=True)
        if not html_str or len(html_str) < 500: return
        lyrics = None
        if "uta-net.com" in url:    _, ly = _extract_lyrics_utanet(html_str);  lyrics = ly
        elif "utaten.com" in url:   _, ly = _extract_lyrics_utaten(html_str);  lyrics = ly
        elif "j-lyric.net" in url:  _, ly = _extract_lyrics_jlyric(html_str);  lyrics = ly
        else:                        _, gl = _parse_generic_lyrics(html_str, query); lyrics = gl
        if not lyrics or len(lyrics) < 40: return
        q_norm = normalize_for_match(query)
        score = 80
        if q_norm in normalize_for_match(lyrics): score += 50
        score += min(30, sum(1 for ln in lyrics.strip().splitlines() if 8 <= len(ln.strip()) <= 80) * 2)
        # 信頼サイトボーナス（まとめ・ブログは0点）
        score += _lyrics_url_score_bonus(url, is_eng)
        with lock:
            if not any(r[2] == lyrics for r in results):
                results.append((score, url, lyrics))
    except Exception as e:
        print(f"{C['y']}[WARN] 歌詞スクレイプ失敗({url[:40]}): {e}{C['w']}")

def _fetch_snippets_from(html: str) -> list[str]:
    return [strip_tags(s) for s in re.findall(r'''class=["']result-snippet["'][^>]*>(.*?)</td>''', html, re.I | re.S) if len(strip_tags(s).strip()) > 15]

# ── 歌詞URLフィルタ ──────────────────────────────────────────────────────────
# まとめ・ブログ・SNS等を除外し、歌詞専門サイトのみ通す
_LYRICS_BLOCKED = {
    # まとめ・ブログ
    "ameblo.jp", "ameba.jp", "livedoor", "fc2.com",
    "hatenablog.com", "hatena.ne.jp", "seesaa.net", "jugem.jp",
    "note.com", "qiita.com", "zenn.dev", "medium.com",
    # まとめ系
    "matome.naver.jp", "togetter.com", "naver.com",
    # SNS・動画
    "twitter.com", "x.com", "instagram.com", "tiktok.com",
    "youtube.com", "youtu.be", "nicovideo.jp", "nico.ms",
    "facebook.com", "pinterest.com",
    # Q&A
    "chiebukuro.yahoo.co.jp", "okwave.jp", "yahoo.co.jp", "yahoo.com",
    # 通販
    "amazon.co.jp", "amazon.com", "rakuten.co.jp", "mercari.com",
    # Wiki
    "wikipedia.org", "wikiwiki.jp", "atwiki.jp",
    # ニュース・音楽情報（歌詞なし）
    "oricon.co.jp", "natalie.mu", "barks.jp", "tower.jp",
    "billboard-japan.com", "musicman.co.jp", "music.apple.com",
    "spotify.com", "recochoku.jp",
}
_LYRICS_TRUSTED_JP = {
    "uta-net.com", "j-lyric.net", "utaten.com",
    "kashinavi.com", "lyric.evesta.jp",
}
_LYRICS_TRUSTED_EN = {
    "genius.com", "azlyrics.com", "musixmatch.com",
    "lyrics.com", "metrolyrics.com",
}

def _is_lyrics_url_ok(url: str, is_eng: bool = False) -> bool:
    try:
        host = U.urlparse(url).netloc.lower() if hasattr(U, 'urlparse') else url
    except Exception:
        host = url
    for b in _LYRICS_BLOCKED:
        if b in host:
            return False
    return True

def _lyrics_url_score_bonus(url: str, is_eng: bool = False) -> int:
    """信頼できる歌詞サイトなら+40点"""
    trusted = _LYRICS_TRUSTED_EN if is_eng else _LYRICS_TRUSTED_JP
    for t in trusted:
        if t in url:
            return 40
    return 0

def _fetch_urls_from(html: str, is_eng: bool = False) -> list[str]:
    urls = []
    for raw in re.findall(r'href=["\'](https?://[^"\']+?)["\']', html, re.I):
        u = U.unquote(raw)
        if u not in urls and _is_lyrics_url_ok(u, is_eng):
            urls.append(u)
    return urls

def search_lyrics_absolute(query: str) -> tuple[str | None, str | None, str | None]:
    is_eng = bool(sum(1 for c in query if ord(c) < 128 and c.isalpha()) > len(query.strip()) * 0.5)
    ddg_urls: list[str] = []
    try:
        kl = "us-en" if is_eng else "jp-jp"
        suffix = " lyrics" if is_eng else " 歌詞"
        # 「まとめサイト」「ブログ」を除外するサイト限定クエリ
        if is_eng:
            site_hint = " (site:genius.com OR site:azlyrics.com OR site:musixmatch.com)"
        else:
            site_hint = " (site:uta-net.com OR site:j-lyric.net OR site:utaten.com)"
        q = query + suffix + site_hint
        data = U.urlencode({"q": q, "kl": kl}).encode("utf-8")
        h = fetch_html("https://lite.duckduckgo.com/lite/", data=data, timeout=4, silent=True)
        ddg_urls = _fetch_urls_from(h, is_eng)
        # site限定で0件なら通常クエリにフォールバック
        if len(ddg_urls) < 2:
            data2 = U.urlencode({"q": query + suffix, "kl": kl}).encode("utf-8")
            h2 = fetch_html("https://lite.duckduckgo.com/lite/", data=data2, timeout=4, silent=True)
            for u in _fetch_urls_from(h2, is_eng):
                if u not in ddg_urls:
                    ddg_urls.append(u)
    except Exception as e:
        print(f"{C['y']}[WARN] DDG検索失敗: {e}{C['w']}")

    candidates = ddg_urls[:8]
    enc_q = U.quote(unicodedata.normalize("NFKC", query).strip())

    # 直接URL（信頼サイトのみ）
    if is_eng:
        extra_urls = [
            f"https://www.azlyrics.com/lyrics/{enc_q.replace('%20','').lower()}.html",
            f"https://genius.com/search?q={enc_q}",
        ]
    else:
        extra_urls = [
            f"https://search.j-lyric.net/index.php?kt={enc_q}&ct=2",
            f"https://www.uta-net.com/search/?Keyword={enc_q}&Aselect=4&Bselect=3",
            f"https://utaten.com/lyric/search/?title={enc_q}",
        ]
    for search_url in extra_urls:
        try:
            h3 = fetch_html(search_url, timeout=3, silent=True, spoof_bot=True)
            for u in _fetch_urls_from(h3, is_eng):
                if u not in candidates:
                    candidates.append(u)
        except Exception as e:
            print(f"{C['y']}[WARN] 歌詞サイト検索失敗: {e}{C['w']}")

    page_results: list = []
    page_lock = threading.Lock()
    threads = [
        threading.Thread(
            target=_scrape_page_parallel,
            args=(u, query, page_results, page_lock),
            daemon=True
        )
        for u in candidates[:10]
    ]
    for t in threads: t.start()
    for t in threads: t.join(timeout=6)

    if page_results:
        best = max(page_results, key=lambda x: x[0])
        return "web", best[1], best[2]   # (source, url, lyrics)
    return None, None, None

def lyrics_debug(query: str) -> str:
    if is_url(query):
        html_str = fetch_html(query, timeout=6, silent=True, spoof_bot=True)
        if not html_str: return f"{C['r']}fetch failed{C['w']}"
        g_t, g_l = _parse_generic_lyrics(html_str, query)
        return f"{C['c']}generic: title={g_t} lyrics={len(g_l or '')}chars{C['w']}"
    rows = [f"{C['c']}=== LYRICS DEBUG ==={C['w']}"]
    try:
        data = U.urlencode({"q": query + " 歌詞", "kl": "jp-jp"}).encode("utf-8")
        h = fetch_html("https://lite.duckduckgo.com/lite/", data=data, timeout=6, silent=True)
        snips = re.findall(r'class="result-snippet"[^>]*>(.*?)</td>', h, re.I | re.S)
        urls = re.findall(r'href=["\'](https?://[^"\']+?)["\']', h, re.I)
        rows.append(f"snippets: {len(snips)} urls: {len(urls)}")
        for i, url in enumerate(urls[:15], 1): rows.append(f"  {i}. {url[:80]}")
        for i, s in enumerate(snips[:5], 1): rows.append(f"  S{i}: {strip_tags(s)[:60]}")
    except Exception as e: rows.append(f"error: {e}")
    return "\n".join(rows)

# ===== MIDI GENERATION v2 (Enhanced — Multi-Track + Music Theory) =====
import random as _midi_rng

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

# ----- 音楽理論定数 -----
_SCALE_INTERVALS = {
    "major":      [0, 2, 4, 5, 7, 9, 11],
    "minor":      [0, 2, 3, 5, 7, 8, 10],
    "pentatonic": [0, 2, 4, 7, 9],
    "blues":      [0, 3, 5, 6, 7, 10],
    "dorian":     [0, 2, 3, 5, 7, 9, 10],
}
# キー名 → MIDI root (C4=60 基準)
_NOTE_ROOTS = {
    "C":60,"Db":61,"D":62,"Eb":63,"E":64,"F":65,
    "Gb":66,"G":67,"Ab":68,"A":69,"Bb":70,"B":71,
}
# ダイアトニックコード音程 (degree 1-7, major)
_DIATONIC_TRIADS = [
    [0,4,7],[2,5,9],[4,7,11],[5,9,12],[7,11,14],[9,12,16],[11,14,17]
]
# セクション別コード進行 (degree 1-based, 繰り返し)
_CHORD_PROGS = {
    "intro":        [1,6,4,5],
    "verse_A":      [1,5,6,4],
    "verse_B":      [6,4,1,5],
    "chorus":       [1,5,6,4],
    "bridge":       [4,5,3,6],
    "solo":         [1,4,5,5],
    "outro":        [1,6,4,1],
    "interlude":    [4,1,5,6],
    "buildup":      [6,6,4,5],
    "chorus_final": [1,5,6,4],
    "verse_C":      [1,4,6,5],
    "bridge2":      [2,6,4,5],
    "solo2":        [6,4,1,5],
}
# セクション特性
_SEC_TRAITS = {
    "intro":        {"vel":62, "oct":0,  "density":0.50, "nlen":1.00},
    "verse_A":      {"vel":72, "oct":0,  "density":0.65, "nlen":0.75},
    "verse_B":      {"vel":74, "oct":0,  "density":0.70, "nlen":0.75},
    "chorus":       {"vel":90, "oct":0,  "density":0.85, "nlen":0.50},
    "bridge":       {"vel":65, "oct":-1, "density":0.55, "nlen":1.00},
    "solo":         {"vel":88, "oct":1,  "density":0.95, "nlen":0.25},
    "outro":        {"vel":55, "oct":0,  "density":0.40, "nlen":1.50},
    "interlude":    {"vel":68, "oct":0,  "density":0.50, "nlen":1.00},
    "buildup":      {"vel":80, "oct":0,  "density":0.80, "nlen":0.50},
    "chorus_final": {"vel":100,"oct":0,  "density":1.00, "nlen":0.50},
    "verse_C":      {"vel":76, "oct":0,  "density":0.70, "nlen":0.75},
    "bridge2":      {"vel":70, "oct":-1, "density":0.60, "nlen":1.00},
    "solo2":        {"vel":92, "oct":1,  "density":1.00, "nlen":0.25},
}
# GM楽器番号
_GM = {"piano":0,"strings":48,"pad":88,"bass":32,"guitar":25}
# ドラム MIDI音番号
_DRUM = {"kick":36,"snare":38,"hihat":42,"open_hat":46,"crash":49,"ride":51,"tom":45}

def _midi_scale(root: int, stype: str, oct_off: int) -> list[int]:
    """指定ルート・スケールのMIDIピッチリスト（48〜96範囲）"""
    intervals = _SCALE_INTERVALS.get(stype, _SCALE_INTERVALS["major"])
    base = root % 12 + (5 + oct_off) * 12
    pitches = []
    for o in range(-2, 3):
        for iv in intervals:
            p = base + iv + o * 12
            if 36 <= p <= 108:
                pitches.append(p)
    return sorted(set(pitches))

def _chord_pitches(root: int, degree: int, base_oct: int = 4) -> list[int]:
    idx = (degree - 1) % 7
    base = root % 12 + base_oct * 12
    return [max(36, min(96, base + iv)) for iv in _DIATONIC_TRIADS[idx]]

def _gen_melody(root: int, section: str, bars: int, stype: str = "major") -> list[dict]:
    tr  = _SEC_TRAITS.get(section, _SEC_TRAITS["verse_A"])
    sc  = _midi_scale(root, stype, tr["oct"])
    prog = _CHORD_PROGS.get(section, [1,5,6,4])
    rng = _midi_rng.Random(hash(section) % 2**32)
    notes, pprev = [], None
    for bar in range(bars):
        deg = prog[bar % len(prog)]
        ct  = _chord_pitches(root, deg, 5 + tr["oct"])
        ct_set = {p % 12 for p in ct}
        sc_ch = [p for p in sc if p % 12 in ct_set] or sc
        beat = 0.0
        while beat < 4.0:
            if rng.random() > tr["density"]:
                beat += tr["nlen"]; continue
            # 前のノートから近い音を優先（スムーズな動き）
            if pprev is not None:
                candidates = sorted(sc_ch, key=lambda p: abs(p - pprev))[:5]
                weights = [5,4,3,2,1][:len(candidates)]
                pitch = rng.choices(candidates, weights=weights)[0]
            else:
                pitch = rng.choice(sc_ch)
            dur = min(tr["nlen"] * rng.uniform(0.85, 1.2), 4.0 - beat)
            vel = max(40, min(120, tr["vel"] + rng.randint(-8, 8)))
            notes.append({"pitch": pitch, "start": float(bar * 4 + beat),
                          "duration": round(max(0.1, dur), 3), "velocity": vel})
            pprev = pitch
            beat += tr["nlen"]
    return notes

def _gen_chords(root: int, section: str, bars: int) -> list[dict]:
    tr   = _SEC_TRAITS.get(section, _SEC_TRAITS["verse_A"])
    prog = _CHORD_PROGS.get(section, [1,5,6,4])
    rng  = _midi_rng.Random(hash(section + "ch") % 2**32)
    notes = []
    for bar in range(bars):
        deg = prog[bar % len(prog)]
        pts = _chord_pitches(root, deg, 4)
        if section in ("chorus","chorus_final","buildup"):
            beats = [0.0, 2.0]
        elif section in ("solo","solo2","bridge","bridge2"):
            beats = [0.0]
        else:
            beats = [0.0, 2.5]
        for bt in beats:
            if rng.random() > 0.92: continue
            vel = max(30, min(100, int(tr["vel"] * 0.68) + rng.randint(-5,5)))
            dur = 1.8 if bt == 0.0 else 1.2
            for p in pts:
                notes.append({"pitch": p, "start": float(bar*4+bt),
                              "duration": dur, "velocity": vel})
    return notes

def _gen_bass(root: int, section: str, bars: int) -> list[dict]:
    tr   = _SEC_TRAITS.get(section, _SEC_TRAITS["verse_A"])
    prog = _CHORD_PROGS.get(section, [1,5,6,4])
    rng  = _midi_rng.Random(hash(section + "bs") % 2**32)
    notes = []
    for bar in range(bars):
        deg   = prog[bar % len(prog)]
        pts   = _chord_pitches(root, deg, 3)
        rn, fn = pts[0], (pts[2] if len(pts) > 2 else pts[0] + 7)
        rn, fn = max(28, min(52, rn)), max(28, min(52, fn))
        if section in ("intro","outro"):
            notes.append({"pitch": rn, "start": float(bar*4), "duration": 3.5,
                          "velocity": max(55, tr["vel"]-10)})
        elif section in ("chorus","chorus_final","buildup","solo","solo2"):
            for i in range(8):
                p = rn if i%2==0 else (fn if i%4==2 else max(28,min(52, rn+rng.choice([2,5,7]))))
                notes.append({"pitch": p, "start": float(bar*4+i*0.5), "duration": 0.45,
                              "velocity": min(110, tr["vel"]-5+rng.randint(-4,4))})
        else:
            for bt in [0,1,2,3]:
                p = rn if bt in (0,2) else (fn if bt==1 else max(28,min(52, rn-2)))
                notes.append({"pitch": p, "start": float(bar*4+bt), "duration": 0.85,
                              "velocity": min(105, tr["vel"]-8+rng.randint(-4,4))})
    return notes

def _gen_drums(section: str, bars: int) -> list[dict]:
    K,SN,HH,OH,CR = _DRUM["kick"],_DRUM["snare"],_DRUM["hihat"],_DRUM["open_hat"],_DRUM["crash"]
    rng   = _midi_rng.Random(hash(section + "dr") % 2**32)
    notes = []
    vb    = 1.25 if section in ("chorus","chorus_final","buildup") else 1.0
    if section in ("intro",):
        # イントロ: ハイハットのみ、だんだん足される
        for bar in range(bars):
            pct = bar / max(bars-1,1)
            for i in range(8):
                notes.append({"pitch":HH,"start":float(bar*4+i*0.5),"duration":0.1,
                              "velocity":int(45+pct*20+rng.randint(-3,3)),"channel":9})
            if pct > 0.5:  # 後半からキック追加
                notes.append({"pitch":K,"start":float(bar*4),"duration":0.1,"velocity":int(70*pct),"channel":9})
        return notes
    if section in ("outro",):
        for bar in range(bars):
            fade = max(0.2, 1.0 - bar/bars)
            notes.append({"pitch":K, "start":float(bar*4),  "duration":0.1,"velocity":int(80*fade),"channel":9})
            notes.append({"pitch":SN,"start":float(bar*4+2),"duration":0.1,"velocity":int(70*fade),"channel":9})
            for i in range(4):
                notes.append({"pitch":HH,"start":float(bar*4+i),"duration":0.1,"velocity":int(45*fade),"channel":9})
        return notes
    for bar in range(bars):
        # クラッシュ: セクション開始
        if bar == 0:
            notes.append({"pitch":CR,"start":float(bar*4),"duration":0.5,"velocity":int(min(127,95*vb)),"channel":9})
        # キック
        kick_beats = [0,1.5,2,3.5] if section in ("chorus","chorus_final","buildup") else [0,2]
        for b in kick_beats:
            notes.append({"pitch":K,"start":float(bar*4+b),"duration":0.1,
                          "velocity":int(min(127,82*vb+rng.randint(-4,4))),"channel":9})
        # スネア
        for b in [1,3]:
            notes.append({"pitch":SN,"start":float(bar*4+b),"duration":0.1,
                          "velocity":int(min(120,78*vb+rng.randint(-4,4))),"channel":9})
        # ハイハット
        hh_div = 8 if section in ("chorus","chorus_final","solo","solo2","buildup") else 4
        for i in range(hh_div):
            is_open = (i == hh_div-1 and rng.random() > 0.75)
            notes.append({"pitch": OH if is_open else HH,
                          "start": float(bar*4 + i*(4.0/hh_div)),
                          "duration": 0.1, "velocity": int(50+rng.randint(-5,10)), "channel":9})
    return notes

def _midi_section_prompt(theme: str, section: str, bars: int, tempo: int, key: str,
                          chord_prog: list) -> list[dict]:
    """改良版LLMメロディープロンプト（コード進行付き）"""
    cdesc = {1:"I",2:"IIm",3:"IIIm",4:"IV",5:"V",6:"VIm",7:"VIIdim"}
    prog_str = " → ".join(cdesc.get(d, str(d)) for d in chord_prog) + " (繰り返し)"
    hi_oct = "高め（ソロ）" if section in ("solo","solo2") else "通常"
    system = (
        f"あなたはプロのMIDI作曲家です。以下の条件でメロディーのMIDIノートを生成してください。\n"
        f"テーマ: {theme} | セクション: {section} | キー: {key}メジャー | テンポ: {tempo}BPM | {bars}小節\n"
        f"コード進行（1小節=1コード）: {prog_str}\n\n"
        f"【生成ルール】\n"
        f"1. コードトーン中心のメロディー（非コード音は短い経過音・装飾音のみ）\n"
        f"2. 音域: MIDI 52〜88（オクターブ: {hi_oct}）\n"
        f"3. 音の動きはスムーズに（基本は順次進行か3度跳躍、ソロは例外OK）\n"
        f"4. start は0〜{bars*4-0.1:.1f}（ビート単位、小節=4ビート）\n"
        f"5. セクション「{section}」らしいリズム感と強弱をつける\n"
        f"6. ノート数: {bars*5}〜{bars*10}個\n\n"
        f"出力: JSONアレイのみ。前置き・説明・コードブロック記法は不要。\n"
        f'形式: [{{"pitch":60,"start":0.0,"duration":0.5,"velocity":80}}, ...]'
    )
    user = f"「{theme}」の{section}セクション、{bars}小節分のメロディーノートを生成してください（{key}メジャー、{tempo}BPM）:"
    return [{"role":"system","content":system},{"role":"user","content":user}]

def _parse_midi_notes(raw: str) -> list[dict]:
    """LLM出力からMIDIノートをパース（堅牢版・複数JSON候補を試行）"""
    candidates = re.findall(r'\[[\s\S]*?\]', raw)
    for m in candidates:
        try:
            arr = json.loads(m)
            if not isinstance(arr, list) or len(arr) < 3: continue
            parsed = []
            for n in arr:
                if not isinstance(n, dict): continue
                if "pitch" not in n or "start" not in n: continue
                parsed.append({
                    "pitch":    max(0,  min(127, int(float(n.get("pitch",60))))),
                    "start":    max(0.0, float(n.get("start",0))),
                    "duration": max(0.1, float(n.get("duration",0.5))),
                    "velocity": max(30,  min(127, int(float(n.get("velocity",75))))),
                    "channel":  int(n.get("channel",0)),
                })
            if len(parsed) >= 3:
                return parsed
        except Exception:
            continue
    return []

def generate_midi_section(theme: str, section: str, bars: int, tempo: int, key: str) -> dict:
    """セクション単位でマルチトラックデータを生成（melody/chords/bass/drums）"""
    root    = _NOTE_ROOTS.get(key, 60)
    prog    = _CHORD_PROGS.get(section, [1,5,6,4])
    # LLMでメロディ生成を試みる
    llm_mel = []
    try:
        raw = stream_response(
            _midi_section_prompt(theme, section, bars, tempo, key, prog),
            True, 200, silent=True, max_tokens=8000
        )
        if raw: llm_mel = _parse_midi_notes(raw)
    except Exception: pass
    # LLM失敗 or ノート不足 → アルゴリズム生成
    melody = llm_mel if len(llm_mel) >= bars * 3 else _gen_melody(root, section, bars)
    return {
        "melody": melody,
        "chords": _gen_chords(root, section, bars),
        "bass":   _gen_bass(root, section, bars),
        "drums":  _gen_drums(section, bars),
    }

def save_midi(all_sections: list, tempo: int, path: str) -> bool:
    """マルチトラック（melody/chords/bass/drums）MIDIファイルを保存"""
    try: from midiutil import MIDIFile
    except ImportError: return False
    # 4トラック構成
    midi = MIDIFile(4)
    track_info = [("Melody",0),("Chords",1),("Bass",2),("Drums",9)]
    for ti, (tname, _) in enumerate(track_info):
        midi.addTempo(ti, 0, tempo)
        midi.addTrackName(ti, 0, tname)
    # GM楽器設定 (ch9はドラム固定なので設定不要)
    for ti, (_, ch) in enumerate(track_info):
        if ch != 9:
            gm = [_GM["piano"], _GM["strings"], _GM["bass"]][ti]
            midi.addProgramChange(ti, ch, 0, gm)
    offset = 0.0
    track_keys = ["melody","chords","bass","drums"]
    for sec_name, tracks in all_sections:
        all_flat = []
        for tk, (_, ch) in zip(track_keys, track_info):
            for n in tracks.get(tk, []):
                pitch    = max(0,  min(127, n["pitch"]))
                start    = n["start"] + offset
                dur      = max(0.05, n["duration"])
                vel      = max(1,   min(127, n["velocity"]))
                act_ch   = n.get("channel", ch)
                ti       = track_keys.index(tk)
                midi.addNote(ti, act_ch, pitch, start, dur, vel)
                all_flat.append(n)
        # セクション長を算出してオフセット更新（ギャップなし）
        if all_flat:
            offset += max(n["start"] + n["duration"] for n in all_flat)
        else:
            offset += 16.0
    with open(path, "wb") as f: midi.writeFile(f)
    return True

def handle_midi(arg: str) -> str:
    if not arg:
        return (f"{C['r']}usage: /midi <テーマ> [short|medium|long|ultra] [BPM] [キー]{C['w']}")
    parts = arg.split()
    length, tempo, key = "medium", 120, "C"
    rest_parts = []
    for p in parts:
        if p.lower() in ("short","medium","long","ultra"): length = p.lower()
        elif p.isdigit() and 60 <= int(p) <= 240:         tempo = int(p)
        elif re.match(r'^[A-G]b?$', p):                   key = p
        else: rest_parts.append(p)
    theme = " ".join(rest_parts) or "インストゥルメンタル"
    sections_plan = MIDI_SECTIONS[length]
    total_bars    = sum(b for _, b in sections_plan)
    print(f"{C['c']}♩ MIDI v2 生成: 『{theme}』 {key}メジャー {tempo}BPM {length}({total_bars}小節) — 4トラック{C['w']}")
    try: from midiutil import MIDIFile
    except ImportError: return f"{C['r']}midiutil未インストール: pip install midiutil{C['w']}"
    all_sections, total_notes = [], 0
    for section, bars in sections_plan:
        print(f"  {C['dim']}[{section}] {bars}小節...{C['w']}", end="", flush=True)
        tracks = generate_midi_section(theme, section, bars, tempo, key)
        all_sections.append((section, tracks))
        cnt = sum(len(v) for v in tracks.values())
        total_notes += cnt
        print(f" {C['g']}{cnt}音 ✓{C['w']}")
    safe_theme = re.sub(r'[^\w]', '_', theme)[:20]
    filename   = f"midi_{safe_theme}_{int(time.time())}.mid"
    if save_midi(all_sections, tempo, filename):
        return (f"{C['g']}♪ 保存完了: {filename}\n"
                f"   {total_notes}音 / {total_bars}小節 / {length}\n"
                f"   トラック: メロディー(piano) + コード(strings) + ベース + ドラム{C['w']}")
    return f"{C['r']}MIDI保存失敗{C['w']}"

def play_singularity(query: str) -> str:
    if not query: return f"{C['r']}曲名を指定してください。{C['w']}"
    ytdl, mpv = shutil.which("yt-dlp"), shutil.which("mpv")
    if not ytdl or not mpv: return f"{C['y']}yt-dlp と mpv が必要です。{C['w']}"
    import secrets
    # PIDベースのファイル名は衝突リスクがあるため安全なランダム名を使用
    out_file = f"ytdl_y_{secrets.token_hex(8)}.wav"
    try:
        r = S.run(
            [ytdl, "-x", "--audio-format", "wav", "-o", out_file, f"ytsearch1:{query}"],
            capture_output=True, text=True, timeout=60
        )
        if r.returncode != 0: return f"{C['r']}failed: {r.stderr[:200]}{C['w']}"
        if os.path.exists(out_file):
            S.Popen([mpv, "--no-video", out_file], stdout=S.DEVNULL, stderr=S.DEVNULL)
            return (
                f"{C['g']}再生開始: {query}{C['w']}\n"
                f"{C['dim']}※ 楽曲の著作権は権利者に帰属します。個人利用の範囲でお使いください。{C['w']}"
            )
        return f"{C['r']}file not found{C['w']}"
    except S.TimeoutExpired:
        return f"{C['r']}timeout{C['w']}"
    except Exception as e:
        return f"{C['r']}error: {e}{C['w']}"


# ===== ローカルRAG: ファイル取り込み・オフライン推論 =====
# 使い方:
#   /kb add <ファイルパス>       テキスト/PDFをベクトルDBに取り込む
#   /kb list                    取り込み済みコレクション一覧
#   /kb search <クエリ>         ローカル知識ベースから検索（ネット不要）
#   /kb ask <質問>              ローカル知識ベース+LLMで回答（完全オフライン）
#   /kb del <コレクション名>    コレクションを削除

BOOK_CHUNK_SIZE = 400
BOOK_CHUNK_OVERLAP = 80
LOCAL_RAG_COLLECTION = "s01_books"

def _chunk_text(text: str, size: int = BOOK_CHUNK_SIZE, overlap: int = BOOK_CHUNK_OVERLAP) -> list[str]:
    """長いテキストを重複ありで分割する。"""
    chunks = []
    start = 0
    while start < len(text):
        end = start + size
        if end < len(text):
            for sep in ("\u3002", "\uff0e", "\n\n", "\n", "\u3001"):
                pos = text.rfind(sep, start + size // 2, end)
                if pos != -1:
                    end = pos + 1
                    break
        chunk = text[start:end].strip()
        if len(chunk) > 30:
            chunks.append(chunk)
        start = end - overlap
    return chunks

def _read_file_text(path: str) -> tuple[str, str]:
    """ファイルを読んでテキストを返す。(text, error_msg)"""
    if not os.path.exists(path):
        return "", f"\u30d5\u30a1\u30a4\u30eb\u304c\u898b\u3064\u304b\u308a\u307e\u305b\u3093: {path}"
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext == ".pdf":
            try:
                import pdfminer.high_level as pdfminer_hl
                text = pdfminer_hl.extract_text(path)
                return text or "", ""
            except ImportError:
                pass
            try:
                import pypdf
                reader = pypdf.PdfReader(path)
                text = "\n".join(p.extract_text() or "" for p in reader.pages)
                return text, ""
            except ImportError:
                return "", "PDF\u3092\u8aad\u3080\u306b\u306f: pip install pdfminer.six"
        elif ext in (".txt", ".md", ".rst", ".csv", ".json"):
            for enc in ("utf-8", "shift_jis", "euc-jp"):
                try:
                    with open(path, "r", encoding=enc) as f:
                        return f.read(), ""
                except UnicodeDecodeError:
                    continue
            return "", "\u6587\u5b57\u30b3\u30fc\u30c9\u3092\u5224\u5b9a\u3067\u304d\u307e\u305b\u3093\u3067\u3057\u305f"
        else:
            return "", f"\u672a\u5bfe\u5fdc\u306e\u5f62\u5f0f: {ext}  (\u5bfe\u5fdc: .txt .md .pdf .rst .csv .json)"
    except Exception as e:
        return "", f"\u8aad\u307f\u8fbc\u307f\u30a8\u30e9\u30fc: {e}"

def _col_name_from_path(path: str) -> str:
    base = os.path.splitext(os.path.basename(path))[0]
    safe = re.sub(r'[^\w\-]', '_', base)[:40].strip("_") or "book"
    return f"book_{safe}"

def handle_kb(arg: str, _chat_fn=None, _persona_id: int = 2) -> str:
    sub, _, rest = arg.partition(" ")
    sub = sub.strip().lower()
    rest = rest.strip()

    if not arg or sub == "list":
        cols = [c for c in vector_list_collections() if c != "s01_memory"]
        if not cols:
            return (f"{C['y']}\u53d6\u308a\u8fbc\u307f\u6e08\u307f\u30d5\u30a1\u30a4\u30eb\u306a\u3057\u3002\n"
                    f"/kb add <\u30d5\u30a1\u30a4\u30eb\u30d1\u30b9> \u3067\u53d6\u308a\u8fbc\u3081\u307e\u3059\uff08.txt .md .pdf \u5bfe\u5fdc\uff09{C['w']}")
        lines = [f"{C['c']}=== \u30ed\u30fc\u30ab\u30eb\u77e5\u8b58\u30d9\u30fc\u30b9 ==={C['w']}"]
        for c in cols:
            n = vector_count(c)
            label = c.replace("book_", "", 1)
            lines.append(f"  {C['g']}{label}{C['w']}  ({n} \u30c1\u30e3\u30f3\u30af)")
        lines.append(f"\n\u4f7f\u3044\u65b9: /kb ask <\u8cea\u554f>  /kb search <\u30ad\u30fc\u30ef\u30fc\u30c9>  /kb del <\u540d\u524d>")
        return "\n".join(lines)

    if sub == "add":
        if not rest:
            return f"{C['r']}usage: /kb add <ファイルパスまたはURL>  例: /kb add https://ja.wikipedia.org/wiki/言語ゲーム{C['w']}"

        # ── URL対応 ───────────────────────────────────────────────
        if rest.startswith("http://") or rest.startswith("https://"):
            # SSRF防止: 内部ネットワークへのアクセスを拒否
            try:
                _assert_safe_url(rest)
            except ValueError as e:
                return f"{C['r']}セキュリティエラー: {e}{C['w']}"
            print(f"{C['c']}[KB] URL取得中: {rest[:80]}{C['w']}")
            raw_html = fetch_html(rest, timeout=10, silent=False, spoof_bot=True)
            if not raw_html:
                return f"{C['r']}URLの取得に失敗しました: {rest}{C['w']}"
            text = strip_tags(raw_html)
            # 余分な空行・ナビゲーション断片を除去
            lines = [l.strip() for l in text.splitlines() if len(l.strip()) > 20]
            text = "\n".join(lines)
            if len(text.strip()) < 50:
                return f"{C['r']}取得できたテキストが短すぎます（{len(text)}文字）{C['w']}"
            # コレクション名はドメイン+パス末尾から生成
            import urllib.parse as _UP
            _parsed = _UP.urlparse(rest)
            _slug = (_parsed.netloc + _parsed.path).rstrip("/").replace("/", "_").replace(".", "_")[:40]
            col_name = f"book_{_slug}"
            chunks = _chunk_text(text)
            print(f"{C['c']}[KB] {len(chunks)}チャンク → コレクション「{_slug}」{C['w']}")
            ok = 0
            for i, chunk in enumerate(chunks):
                if vector_add(chunk, {"source": rest, "chunk": i, "type": "web"}, collection=col_name):
                    ok += 1
                if (i + 1) % 50 == 0:
                    print(f"{C['dim']}  {i+1}/{len(chunks)} チャンク完了...{C['w']}")
            return (f"{C['g']}取り込み完了: {rest[:60]}\n"
                    f"  {ok}/{len(chunks)} チャンク → コレクション「{_slug}」{C['w']}\n"
                    f"{C['dim']}※ 取り込んだコンテンツの著作権は原著作者に帰属します。個人的な学習・研究目的の範囲でご利用ください。{C['w']}")

        # ── ファイルパス ──────────────────────────────────────────
        # パストラバーサル防止（カレントディレクトリ外のファイルを許可しない）
        try:
            _assert_safe_path(rest)
        except ValueError as e:
            return f"{C['r']}セキュリティエラー: {e}{C['w']}"
        text, err = _read_file_text(rest)
        if err: return f"{C['r']}{err}{C['w']}"
        if len(text.strip()) < 50:
            return f"{C['r']}\u30c6\u30ad\u30b9\u30c8\u304c\u77ed\u3059\u304e\u307e\u3059\uff08{len(text)}\u6587\u5b57\uff09{C['w']}"
        col_name = _col_name_from_path(rest)
        chunks = _chunk_text(text)
        print(f"{C['c']}[KB] \u53d6\u308a\u8fbc\u307f\u958b\u59cb: {os.path.basename(rest)} \u2192 {len(chunks)}\u30c1\u30e3\u30f3\u30af{C['w']}")
        ok = 0
        for i, chunk in enumerate(chunks):
            if vector_add(chunk, {"source": rest, "chunk": i, "type": "book"}, collection=col_name):
                ok += 1
            if (i + 1) % 50 == 0:
                print(f"{C['dim']}  {i+1}/{len(chunks)} \u30c1\u30e3\u30f3\u30af\u5b8c\u4e86...{C['w']}")
        return (f"{C['g']}\u53d6\u308a\u8fbc\u307f\u5b8c\u4e86: {os.path.basename(rest)}\n"
                f"  {ok}/{len(chunks)} \u30c1\u30e3\u30f3\u30af \u2192 \u30b3\u30ec\u30af\u30b7\u30e7\u30f3\u300c{col_name.replace('book_','')}\u300d{C['w']}\n"
                f"{C['dim']}※ 著作権のある資料は個人的な学習・研究目的の範囲でご利用ください。{C['w']}")

    if sub == "del":
        if not rest: return f"{C['r']}usage: /kb del <\u30b3\u30ec\u30af\u30b7\u30e7\u30f3\u540d>{C['w']}"
        col_name = rest if rest.startswith("book_") else f"book_{rest}"
        if not VECTOR_AVAILABLE: _init_vector_db()
        try:
            _VECTOR_CLIENT.delete_collection(col_name)
            _VECTOR_COLS.pop(col_name, None)
            return f"{C['y']}\u524a\u9664: {rest}{C['w']}"
        except Exception as e:
            return f"{C['r']}\u524a\u9664\u5931\u6557: {e}{C['w']}"

    if sub == "search":
        if not rest: return f"{C['r']}usage: /kb search <\u30ad\u30fc\u30ef\u30fc\u30c9>{C['w']}"
        cols = [c for c in vector_list_collections() if c != "s01_memory"]
        if not cols: return f"{C['y']}\u53d6\u308a\u8fbc\u307f\u6e08\u307f\u30d5\u30a1\u30a4\u30eb\u306a\u3057\u3002{C['w']}"
        all_hits = []
        for col in cols:
            for h in vector_search(rest, n=3, collection=col):
                all_hits.append((col.replace("book_", ""), h))
        if not all_hits: return f"{C['y']}\u300c{rest}\u300d\u306b\u95a2\u9023\u3059\u308b\u7b87\u6240\u304c\u898b\u3064\u304b\u308a\u307e\u305b\u3093\u3067\u3057\u305f\u3002{C['w']}"
        lines = [f"{C['c']}=== \u691c\u7d22\u7d50\u679c: {rest} ==={C['w']}"]
        for src, hit in all_hits[:6]:
            lines.append(f"\n{C['dim']}[{src}]{C['w']}\n{hit[:300]}")
        return "\n".join(lines)

    if sub == "ask":
        if not rest: return f"{C['r']}usage: /kb ask <質問>  例: /kb ask 言語ゲームとは何か{C['w']}"
        cols = [c for c in vector_list_collections() if c != "s01_memory"]
        if not cols: return f"{C['y']}取り込み済みファイルなし。{C['w']}"

        # ── Pass1: 1次ベクトル検索 ────────────────────────────────
        cite_map: list[tuple[str, str]] = []  # (source_label, chunk_text)
        for col in cols:
            src = col.replace("book_", "")
            for h in vector_search(rest, n=4, collection=col):
                cite_map.append((src, h))
        if not cite_map:
            return f"{C['y']}「{rest}」に関連する箇所が知識ベースに見つかりませんでした。{C['w']}"

        def _build_context(pairs: list[tuple[str, str]]) -> str:
            by_src: dict[str, list[str]] = {}
            for s, chunk in pairs:
                by_src.setdefault(s, []).append(chunk)
            return "\n\n".join(f"《{s}》より\n" + "\n---\n".join(chunks) for s, chunks in by_src.items())

        context = _build_context(cite_map)
        if _chat_fn is None:
            return f"{C['c']}[KB参考文献]{C['w']}\n{context[:800]}"

        from_persona = get_persona(_persona_id)
        fp = from_persona.get("first_person", "私")
        sys_content = (
            f"あなたは{from_persona['name']}。口調: {from_persona['style']}。一人称: {fp}。\n"
            f"以下の「局所参照」の文章のみを根拠にして質問に答えよ。\n"
            f"「局所参照」にない情報は一切追加するな。捕捉・一般論禁止。"
        )
        print(f"{C['c']}[KBオフライン推論 Pass1]{C['w']} {from_persona['name']}: ", end="", flush=True)
        msgs1 = [
            {"role": "system", "content": sys_content},
            {"role": "user", "content": f"「局所参照」:\n{context}\n\n質問: {rest}"}
        ]
        result1 = stream_response(msgs1, True, len(rest), temp_override=0.0, model=DEEP_MODEL) or ""

        # ── Pass2: 1次回答のキーワードで追加検索（マルチホップ）────
        result_final = result1
        if result1:
            hop_kw = extract_keywords(result1, top_n=4)
            hop_query = " ".join(hop_kw)
            if hop_query and hop_query.strip() != rest.strip():
                new_pairs: list[tuple[str, str]] = []
                existing_chunks = {c for _, c in cite_map}
                for col in cols:
                    src = col.replace("book_", "")
                    for h in vector_search(hop_query, n=2, collection=col):
                        if h not in existing_chunks:
                            new_pairs.append((src, h))
                            existing_chunks.add(h)
                if new_pairs:
                    cite_map.extend(new_pairs)
                    extra_ctx = _build_context(new_pairs)
                    print(f"\n{C['dim']}[Pass2: +{len(new_pairs)}チャンク追加 kw={hop_query[:40]}]{C['w']}")
                    print(f"{C['c']}[KBオフライン推論 Pass2]{C['w']} {from_persona['name']}: ", end="", flush=True)
                    msgs2 = [
                        {"role": "system", "content": sys_content},
                        {"role": "user", "content": (
                            f"「局所参照」:\n{context}\n\n「追加参照」:\n{extra_ctx}\n\n"
                            f"質問: {rest}\n\n暫定回答: {result1}\n\n"
                            f"追加参照も踏まえて最終回答を出せ。新情報がなければ暫定回答をそのまま使え。"
                        )}
                    ]
                    result_final = stream_response(msgs2, True, len(rest), temp_override=0.0, model=DEEP_MODEL) or result1

        # ── 引用元を末尾に表示 ─────────────────────────────────────
        if result_final:
            cited_srcs = list(dict.fromkeys(s for s, _ in cite_map))
            cite_str = "  ".join(f"《{s}》" for s in cited_srcs)
            print(f"\n{C['dim']}[参照元: {cite_str} / {len(cite_map)}チャンク]{C['w']}")
            _print_hallucination_warnings(result_final, strict=True)
        return result_final

    return f"{C['r']}usage: /kb add|list|search|ask|del{C['w']}"


# ===================================================================
# SPI / 玉手箱 対策モジュール
# /spi          ランダム出題（言語+非言語ミックス）
# /spi 言語     言語問題のみ
# /spi 非言語   非言語問題のみ
# /spi 英語     英語問題のみ（玉手箱対策）
# /spi 模擬     10問連続模擬試験モード
# /spi 成績     正答率・カテゴリ別統計
# /spi リセット 成績リセット
# ===================================================================

import random as _random

# ---------- 問題データベース ----------
_SPI_DB: list[dict] = [

    # ===== 言語：語句の意味 =====
    {"cat": "言語", "sub": "語句意味", "q": "「示唆」の意味として最も適切なものを選べ。",
     "choices": ["A: それとなく示すこと", "B: 強く命令すること", "C: 完全に否定すること", "D: 詳しく説明すること"],
     "ans": "A", "exp": "示唆＝それとなくほのめかすこと。suggestに近い。"},

    {"cat": "言語", "sub": "語句意味", "q": "「恣意的」の意味として最も適切なものを選べ。",
     "choices": ["A: 慎重で計画的なさま", "B: 自分の思うままで勝手なさま", "C: 周囲に配慮するさま", "D: 論理的に正確なさま"],
     "ans": "B", "exp": "恣意的＝自分の思いのまま、根拠なく決めること。arbitraryに近い。"},

    {"cat": "言語", "sub": "語句意味", "q": "「逡巡」の意味として最も適切なものを選べ。",
      "choices": ["A: 素早く行動すること", "B: ためらってぐずぐずすること", "C: 激しく怒ること", "D: 深く反省すること"],
     "ans": "B", "exp": "逡巡＝ためらい、なかなか決断できないこと。hesitationに近い。"},

    {"cat": "言語", "sub": "語句意味", "q": "「瑣末」の意味として最も適切なものを選べ。",
     "choices": ["A: 非常に重要なこと", "B: 細かくとるに足らないこと", "C: 複雑に絡み合うこと", "D: 急を要すること"],
     "ans": "B", "exp": "瑣末＝細々としてつまらないこと。trivialに近い。"},

    {"cat": "言語", "sub": "語句意味", "q": "「敷衍」の意味として最も適切なものを選べ。",
     "choices": ["A: 意味を押し広げて詳しく説明すること", "B: 強引に押し通すこと", "C: 簡潔にまとめること", "D: 誤りを訂正すること"],
     "ans": "A", "exp": "敷衍＝内容をひろげてわかりやすく説明すること。elaborateに近い。"},

    # ===== 言語：対義語 =====
    {"cat": "言語", "sub": "対義語", "q": "「促進」の対義語として最も適切なものを選べ。",
     "choices": ["A: 抑制", "B: 継続", "C: 加速", "D: 実行"],
     "ans": "A", "exp": "促進（進める）⇔ 抑制（おさえる）。"},

    {"cat": "言語", "sub": "対義語", "q": "「具体」の対義語として最も適切なものを選べ。",
     "choices": ["A: 現実", "B: 抽象", "C: 詳細", "D: 明確"],
     "ans": "B", "exp": "具体（はっきりしたもの）⇔ 抽象（まとめた概念）。"},

    {"cat": "言語", "sub": "対義語", "q": "「楽観」の対義語として最も適切なものを選べ。",
     "choices": ["A: 慎重", "B: 冷静", "C: 悲観", "D: 否定"],
     "ans": "C", "exp": "楽観（よい方向に考える）⇔ 悲観（悪い方向に考える）。"},

    {"cat": "言語", "sub": "対義語", "q": "「冗長」の対義語として最も適切なものを選べ。",
     "choices": ["A: 簡潔", "B: 詳細", "C: 明瞭", "D: 正確"],
     "ans": "A", "exp": "冗長（余分に長い）⇔ 簡潔（短くまとまっている）。"},

    # ===== 言語：文章整序 =====
    {"cat": "言語", "sub": "文章整序", "q": "次のア〜エを意味が通るよう並べ替えたとき、2番目にくるものを選べ。\nア: しかし、そこには大きな落とし穴がある。\nイ: 効率化は現代のビジネスにおいて最優先事項とされている。\nウ: 人間関係や創造性といった要素が犠牲になりやすいのだ。\nエ: 効率のみを追求すると、",
     "choices": ["A: ア", "B: イ", "C: ウ", "D: エ"],
     "ans": "A", "exp": "イ（主張）→ ア（逆接）→ エ（具体化）→ ウ（結論）の順。2番目はア。"},

    # ===== 非言語：割合・比 =====
    {"cat": "非言語", "sub": "割合", "q": "定価1200円の商品を20%引きで買った。支払い金額はいくらか。",
     "choices": ["A: 900円", "B: 960円", "C: 1000円", "D: 1080円"],
     "ans": "B", "exp": "1200 × (1 - 0.20) = 1200 × 0.80 = 960円。"},

    {"cat": "非言語", "sub": "割合", "q": "ある商品を30%値上げした後、さらに10%値引きした。元の価格と比べて何%の変化か。",
     "choices": ["A: 17%増", "B: 20%増", "C: 23%増", "D: 変化なし"],
     "ans": "A", "exp": "1.30 × 0.90 = 1.17 → 元の価格の117%。つまり17%増。"},

    {"cat": "非言語", "sub": "割合", "q": "原価の40%の利益を見込んで定価をつけた。定価2800円のとき、原価はいくらか。",
     "choices": ["A: 1800円", "B: 2000円", "C: 2100円", "D: 2200円"],
     "ans": "B", "exp": "定価 = 原価 × 1.40 → 原価 = 2800 ÷ 1.40 = 2000円。"},

    # ===== 非言語：速度・距離・時間 =====
    {"cat": "非言語", "sub": "速度", "q": "時速60kmで2時間30分走ったときの距離は何kmか。",
     "choices": ["A: 120km", "B: 140km", "C: 150km", "D: 180km"],
     "ans": "C", "exp": "60 × 2.5 = 150km。2時間30分 = 2.5時間。"},

    {"cat": "非言語", "sub": "速度", "q": "A地点からB地点まで時速40kmで行き、帰りは時速60kmで戻った。平均時速はいくらか。",
     "choices": ["A: 48km/h", "B: 50km/h", "C: 52km/h", "D: 54km/h"],
     "ans": "A", "exp": "往復の平均速度 = 2×40×60÷(40+60) = 4800÷100 = 48km/h。単純平均ではなく調和平均を使う。"},

    {"cat": "非言語", "sub": "速度", "q": "600mの道を歩くと10分かかる。同じ道を自転車では3分でいける。自転車の速さは歩きの何倍か。",
     "choices": ["A: 2倍", "B: 3倍", "C: 3.3倍", "D: 4倍"],
     "ans": "C", "exp": "歩き速度: 600÷10=60m/分。自転車: 600÷3=200m/分。200÷60≒3.3倍。"},

    # ===== 非言語：確率 =====
    {"cat": "非言語", "sub": "確率", "q": "1〜6のサイコロを2回振る。2回とも偶数が出る確率はいくらか。",
     "choices": ["A: 1/6", "B: 1/4", "C: 1/3", "D: 1/2"],
     "ans": "B", "exp": "1回で偶数(2,4,6)が出る確率=3/6=1/2。2回とも: 1/2×1/2=1/4。"},

    {"cat": "非言語", "sub": "確率", "q": "袋の中に赤玉3個・白玉2個がある。2個同時に取り出したとき、2個とも同じ色になる確率はいくらか。",
     "choices": ["A: 2/5", "B: 3/10", "C: 7/10", "D: 4/10"],
     "ans": "A", "exp": "全組合せ: C(5,2)=10。同色: C(3,2)+C(2,2)=3+1=4。確率=4/10=2/5。AとDは同値だがAが正式な既約分数。"},

    {"cat": "非言語", "sub": "確率", "q": "コインを3回投げる。少なくとも1回表が出る確率はいくらか。",
     "choices": ["A: 1/2", "B: 5/8", "C: 7/8", "D: 3/4"],
     "ans": "C", "exp": "1 − (全部裏の確率) = 1 − (1/2)³ = 1 − 1/8 = 7/8。余事象を使うと簡単。"},

    # ===== 非言語：推論・集合 =====
    {"cat": "非言語", "sub": "推論", "q": "「全ての社員はA研修を受けた」「BさんはA研修を受けていない」から確実に言えることを選べ。",
     "choices": ["A: BさんはA研修に合格した", "B: Bさんは社員ではない", "C: 社員はB研修も受けた", "D: BさんはA研修を受けるべきだ"],
     "ans": "B", "exp": "三段論法: 全社員→A研修済。B→A研修未。よってBは社員でない。"},

    {"cat": "非言語", "sub": "集合", "q": "100人のうち英語ができる人60人、中国語ができる人50人、両方できる人20人。どちらもできない人は何人か。",
     "choices": ["A: 10人", "B: 20人", "C: 30人", "D: 40人"],
     "ans": "A", "exp": "英語のみ+中国語のみ+両方 = 40+30+20 = 90人。どちらもできない = 100−90 = 10人。"},

    # ===== 非言語：図表 =====
    {"cat": "非言語", "sub": "図表", "q": "ある会社の売上が2020年100万円、2021年120万円、2022年108万円だった。2021年から2022年の変化率はいくらか。",
     "choices": ["A: −10%", "B: −8%", "C: +8%", "D: +10%"],
     "ans": "A", "exp": "(108−120)÷120 = −12÷120 = −0.10 = −10%。"},

    # ===== 英語（玉手箱） =====
    {"cat": "英語", "sub": "同意語", "q": "「ambiguous」と最も意味が近い語を選べ。",
     "choices": ["A: clear", "B: vague", "C: accurate", "D: simple"],
     "ans": "B", "exp": "ambiguous＝あいまいな。vague（漠然とした）が最も近い。"},

    {"cat": "英語", "sub": "同意語", "q": "「diligent」と最も意味が近い語を選べ。",
     "choices": ["A: lazy", "B: clever", "C: hardworking", "D: quiet"],
     "ans": "C", "exp": "diligent＝勤勉な。hardworking（よく働く）が最も近い。"},

    {"cat": "英語", "sub": "同意語", "q": "「concise」と最も意味が近い語を選べ。",
     "choices": ["A: brief", "B: detailed", "C: complex", "D: extended"],
     "ans": "A", "exp": "concise＝簡潔な。brief（短く要領を得た）が最も近い。"},

    {"cat": "英語", "sub": "同意語", "q": "「inevitable」と最も意味が近い語を選べ。",
     "choices": ["A: avoidable", "B: unexpected", "C: uncertain", "D: unavoidable"],
     "ans": "D", "exp": "inevitable＝避けられない。unavoidable（回避不可能な）が最も近い。"},

    {"cat": "英語", "sub": "英文読解", "q": "次の英文の内容と一致するものを選べ。\n\"The key to effective communication is not just speaking clearly, but also listening actively.\"",
     "choices": ["A: 明確に話すことだけが重要だ", "B: 積極的に聞くことも重要だ", "C: コミュニケーションは話すことで完結する", "D: 聞くことより話すことが優先される"],
     "ans": "B", "exp": "not just A but also B（AだけでなくBも）。listeningも重要と言っている。"},

    # ===== 英語：同意語追加 =====
    {"cat": "英語", "sub": "同意語", "q": "「adequate」と最も意味が近い語を選べ。",
     "choices": ["A: excellent", "B: sufficient", "C: lacking", "D: complex"],
     "ans": "B", "exp": "adequate＝十分な。sufficient（足りている）が最も近い。"},

    {"cat": "英語", "sub": "同意語", "q": "「obsolete」と最も意味が近い語を選べ。",
     "choices": ["A: modern", "B: useful", "C: outdated", "D: popular"],
     "ans": "C", "exp": "obsolete＝時代遅れの・廃れた。outdated（古くなった）が最も近い。"},

    {"cat": "英語", "sub": "同意語", "q": "「transparent」と最も意味が近い語を選べ。",
     "choices": ["A: hidden", "B: clear", "C: heavy", "D: slow"],
     "ans": "B", "exp": "transparent＝透明な・明白な。clear（明確な）が最も近い。"},

    # ===== 玉手箱：四則逆算 =====
    # 形式：□に入る数を選ぶ。速度が命。
    {"cat": "玉手箱", "sub": "四則逆算", "q": "□ × 7 = 56　　□に入る数はいくつか。",
     "choices": ["A: 6", "B: 7", "C: 8", "D: 9"],
     "ans": "C", "exp": "56 ÷ 7 = 8。掛け算の逆算は割り算。"},

    {"cat": "玉手箱", "sub": "四則逆算", "q": "72 ÷ □ = 9　　□に入る数はいくつか。",
     "choices": ["A: 6", "B: 7", "C: 8", "D: 9"],
     "ans": "C", "exp": "72 ÷ 9 = 8。割り算の逆算は割り算（72÷9）。"},

    {"cat": "玉手箱", "sub": "四則逆算", "q": "□ + 47 = 83　　□に入る数はいくつか。",
     "choices": ["A: 34", "B: 36", "C: 38", "D: 40"],
     "ans": "B", "exp": "83 − 47 = 36。足し算の逆算は引き算。"},

    {"cat": "玉手箱", "sub": "四則逆算", "q": "125 − □ = 68　　□に入る数はいくつか。",
     "choices": ["A: 53", "B: 55", "C: 57", "D: 59"],
     "ans": "C", "exp": "125 − 68 = 57。引き算の逆算: □ = 125 − 68。"},

    {"cat": "玉手箱", "sub": "四則逆算", "q": "□ ÷ 6 = 13　　□に入る数はいくつか。",
     "choices": ["A: 72", "B: 78", "C: 80", "D: 84"],
     "ans": "B", "exp": "13 × 6 = 78。割り算の逆算は掛け算。"},

    {"cat": "玉手箱", "sub": "四則逆算", "q": "3 × □ − 5 = 19　　□に入る数はいくつか。",
     "choices": ["A: 6", "B: 7", "C: 8", "D: 9"],
     "ans": "C", "exp": "3×□ = 19+5 = 24 → □ = 24÷3 = 8。後ろから逆算する。"},

    {"cat": "玉手箱", "sub": "四則逆算", "q": "(□ + 4) × 3 = 27　　□に入る数はいくつか。",
     "choices": ["A: 5", "B: 7", "C: 9", "D: 11"],
     "ans": "A", "exp": "□ + 4 = 27÷3 = 9 → □ = 9−4 = 5。括弧の外から逆算。"},

    {"cat": "玉手箱", "sub": "四則逆算", "q": "48 ÷ (□ − 2) = 6　　□に入る数はいくつか。",
     "choices": ["A: 8", "B: 9", "C: 10", "D: 12"],
     "ans": "C", "exp": "□−2 = 48÷6 = 8 → □ = 10。"},

    # ===== 玉手箱：長文一致（一致・不一致・どちらとも言えない の3択） =====
    {"cat": "玉手箱", "sub": "長文一致", "q": (
        "【本文】\n"
        "日本の食品ロスは年間約600万トンとされており、そのうち約半分は家庭から発生している。"
        "食品ロス削減のためには、企業だけでなく消費者一人ひとりの取り組みが不可欠である。\n\n"
        "【設問】「食品ロスの半分以上は企業活動から発生している」\n"
        "本文の内容と比較して、この記述は？"
    ),
     "choices": ["A: 一致する", "B: 一致しない", "C: どちらとも言えない"],
     "ans": "B", "exp": "本文では「約半分は家庭から」とあるため、企業が半分以上というのは不一致。"},

    {"cat": "玉手箱", "sub": "長文一致", "q": (
        "【本文】\n"
        "リモートワークの普及により、都市部から地方への人口移動が緩やかに進んでいる。"
        "ただし、この傾向は主にIT関連職種において顕著であり、全業種への波及は限定的とされる。\n\n"
        "【設問】「IT関連職種ではリモートワークを機に地方移住が進んでいる」\n"
        "本文の内容と比較して、この記述は？"
    ),
     "choices": ["A: 一致する", "B: 一致しない", "C: どちらとも言えない"],
     "ans": "A", "exp": "本文「IT関連職種において顕著」と一致する。"},

    {"cat": "玉手箱", "sub": "長文一致", "q": (
        "【本文】\n"
        "近年、Z世代を中心に「タイパ（タイムパフォーマンス）」を重視する傾向が強まっている。"
        "動画を倍速視聴したり、結末から確認してから作品を観るといった行動がその典型例とされる。\n\n"
        "【設問】「タイパ重視の傾向はすべての世代で同様に見られる」\n"
        "本文の内容と比較して、この記述は？"
    ),
     "choices": ["A: 一致する", "B: 一致しない", "C: どちらとも言えない"],
     "ans": "B", "exp": "本文では「Z世代を中心に」とあり、全世代とは書かれていない。不一致。"},

    {"cat": "玉手箱", "sub": "長文一致", "q": (
        "【本文】\n"
        "再生可能エネルギーの導入コストはこの10年で大幅に低下した。"
        "太陽光発電のコストは2010年比で約80%削減されたとする試算もある。"
        "しかし蓄電技術の課題は依然として残っており、安定供給には課題がある。\n\n"
        "【設問】「蓄電技術の問題が解決されれば再生可能エネルギーは完全に普及する」\n"
        "本文の内容と比較して、この記述は？"
    ),
     "choices": ["A: 一致する", "B: 一致しない", "C: どちらとも言えない"],
     "ans": "C", "exp": "本文は蓄電課題に言及するが、解決後の完全普及については述べていない。「どちらとも言えない」。"},

    # ===== 玉手箱：テーブル問題 =====
    {"cat": "玉手箱", "sub": "テーブル", "q": (
        "下表はA〜C店の月別売上（万円）を示す。\n"
        "┌──────┬────┬────┬────┐\n"
        "│      │ A店 │ B店 │ C店 │\n"
        "├──────┼────┼────┼────┤\n"
        "│ 4月  │ 120 │  90 │ 150 │\n"
        "│ 5月  │ 130 │ 110 │ 140 │\n"
        "│ 6月  │ 110 │ 130 │ 160 │\n"
        "└──────┴────┴────┴────┘\n"
        "3ヶ月の合計売上が最も多い店はどこか。"
    ),
     "choices": ["A: A店", "B: B店", "C: C店", "D: 同じ"],
     "ans": "C", "exp": "A店: 120+130+110=360。B店: 90+110+130=330。C店: 150+140+160=450。C店が最多。"},

    {"cat": "玉手箱", "sub": "テーブル", "q": (
        "下表は社員4人の残業時間（時間/月）を示す。\n"
        "┌──────┬──┬──┬──┬──┐\n"
        "│      │田中│鈴木│佐藤│高橋│\n"
        "├──────┼──┼──┼──┼──┤\n"
        "│ 1月  │ 20 │ 15 │ 30 │ 10 │\n"
        "│ 2月  │ 25 │ 20 │ 20 │ 15 │\n"
        "│ 3月  │ 15 │ 25 │ 25 │ 20 │\n"
        "└──────┴──┴──┴──┴──┘\n"
        "3ヶ月の平均残業時間が最も少ない社員は誰か。"
    ),
     "choices": ["A: 田中", "B: 鈴木", "C: 佐藤", "D: 高橋"],
     "ans": "D", "exp": "田中:60/3=20。鈴木:60/3=20。佐藤:75/3=25。高橋:45/3=15。高橋が最少。"},

    {"cat": "玉手箱", "sub": "テーブル", "q": (
        "下表はある試験の得点分布（人数）を示す。\n"
        "┌──────────┬────┐\n"
        "│ 得点区分   │ 人数 │\n"
        "├──────────┼────┤\n"
        "│ 90点以上   │   5  │\n"
        "│ 70〜89点   │  15  │\n"
        "│ 50〜69点   │  20  │\n"
        "│ 50点未満   │  10  │\n"
        "└──────────┴────┘\n"
        "70点以上の受験者は全体の何%か。"
    ),
     "choices": ["A: 20%", "B: 25%", "C: 40%", "D: 50%"],
     "ans": "C", "exp": "70点以上: 5+15=20人。全体: 5+15+20+10=50人。20÷50=0.40=40%。"},
]

# ---------- 成績管理 ----------
_SPI_SCORE_KEY = "spi_score"

def _spi_load_score() -> dict:
    state = load_state()
    return state.get(_SPI_SCORE_KEY, {"total": 0, "correct": 0, "cats": {}})

def _spi_save_score(sc: dict) -> None:
    state = load_state()
    state[_SPI_SCORE_KEY] = sc
    save_state(state)

def _spi_record(cat: str, correct: bool) -> None:
    sc = _spi_load_score()
    sc["total"] += 1
    if correct: sc["correct"] += 1
    cats = sc.setdefault("cats", {})
    cats.setdefault(cat, {"total": 0, "correct": 0})
    cats[cat]["total"] += 1
    if correct: cats[cat]["correct"] += 1
    _spi_save_score(sc)

# ---------- 出題セッション管理（同一プロセス内） ----------
# セッション状態はload_state()/save_state()で永続化
_SPI_SESSION_KEY = "spi_session"
# ★[修正/spi-3] ファイルI/Oの競合・キャッシュミスによるセッション消失を防ぐため
# メモリ上にもセッションを保持するミラーを追加。
# load/saveは両方に書き込み、loadはメモリを優先して返す。
_SPI_SESSION_MEMORY: dict = {}

def _spi_load_session() -> dict:
    # メモリに有効なセッションがあればそちらを優先（ファイルI/O競合を回避）
    if _SPI_SESSION_MEMORY.get("current") and isinstance(_SPI_SESSION_MEMORY["current"], dict) and len(_SPI_SESSION_MEMORY["current"]) > 0:
        return dict(_SPI_SESSION_MEMORY)
    return load_state().get(_SPI_SESSION_KEY, {
        "current": {}, "mock_queue": [], "mock_results": [], "is_mock": False})

def _spi_save_session(current: dict, queue: list, results: list, is_mock: bool = False) -> None:
    global _SPI_SESSION_MEMORY
    sess = {"current": current, "mock_queue": queue, "mock_results": results, "is_mock": is_mock}
    # メモリに即時反映（ファイル書き込み失敗時のフォールバック）
    _SPI_SESSION_MEMORY = dict(sess)
    state = load_state()
    state[_SPI_SESSION_KEY] = sess
    save_state(state)

def _spi_clear_session() -> None:
    global _SPI_SESSION_MEMORY
    _SPI_SESSION_MEMORY = {}
    state = load_state()
    state.pop(_SPI_SESSION_KEY, None)
    save_state(state)

def _spi_pick(filter_cat: str | None = None) -> dict:
    pool = [q for q in _SPI_DB if filter_cat is None or q["cat"] == filter_cat]
    return _random.choice(pool)

# ---------- 出題履歴管理（ローテーション） ----------
_SPI_USED_IDS: list[str] = []   # 出題済みq_idのリスト（古い順）
_SPI_USED_MAX = 60               # この件数を超えたら古いものを解禁

def _spi_make_id(q: dict) -> str:
    return q.get("q", "")[:30]

def _spi_mark_used(q: dict) -> None:
    qid = _spi_make_id(q)
    if qid in _SPI_USED_IDS:
        _SPI_USED_IDS.remove(qid)
    _SPI_USED_IDS.append(qid)
    if len(_SPI_USED_IDS) > _SPI_USED_MAX:
        _SPI_USED_IDS.pop(0)

def _spi_pick_fresh(filter_cat: str | None = None) -> dict:
    """出題済みを避けてDBから選ぶ。全部出済みならランダム。"""
    pool = [q for q in _SPI_DB if filter_cat is None or q["cat"] == filter_cat]
    fresh = [q for q in pool if _spi_make_id(q) not in _SPI_USED_IDS]
    chosen = _random.choice(fresh) if fresh else _random.choice(pool)
    _spi_mark_used(chosen)
    return chosen

# ---------- LLMによる問題動的生成 ----------
# サブカテゴリ定義（生成指示付き）
_SPI_LLM_SUBTYPES = {
    "言語": [
        ("語句意味",   "「{word}」の意味として最も適切なものを選べ。4択（A/B/C/D）で出題し、正解・不正解の選択肢を作れ。語はSPIで頻出の難読語・ビジネス語から選ぶ。"),
        ("同意語",     "「{word}」と最も意味が近い語を4択で出題せよ。"),
        ("対義語",     "「{word}」の対義語として最も適切な語を4択で出題せよ。"),
        ("文章完成",   "次の文の（　）に入る最も適切な語を4択で選べ。文章はSPIらしい論理的な文にすること。"),
        ("文章整序",   "次のア〜エの文を意味が通る順に並べ替えよ。選択肢は並び順4パターン（A/B/C/D）で出題せよ。"),
        ("長文読解",   "以下の文章を読んで設問に答えよ。本文100字程度・設問は「筆者が述べていること」「本文の内容と一致するもの」等。4択。"),
        ("熟語の意味", "「{word}」の意味として最も適切なものを4択で出題せよ。四字熟語・ことわざ・慣用句から選ぶ。"),
        ("語句用法",   "「{word}」の使い方として正しいものを4択で選べ。誤用しやすい語を選ぶこと。"),
    ],
    "非言語": [
        ("速度・時間・距離", "速さ・時間・距離に関するSPIらしい文章題を1問作れ。4択（A/B/C/D）、数値は整数。"),
        ("割合・比",         "割合や比に関するSPIらしい文章題を1問作れ。4択、数値は整数か単純な小数。"),
        ("損益計算",         "原価・売価・利益率に関するSPIらしい文章題を1問作れ。4択。"),
        ("仕事算",           "AとBが協力して仕事をする問題をSPIらしく作れ。4択。"),
        ("集合・ベン図",     "重複を含む集合（ベン図）の問題をSPIらしく作れ。4択。"),
        ("確率",             "日常的な場面での確率問題をSPIらしく作れ。4択、答えは分数でも可。"),
        ("推論",             "条件が3〜4つ与えられ、正しい結論を選ぶSPI推論問題を作れ。4択。"),
        ("資料解釈",         "表やグラフの数値を読み取る問題をSPIらしく作れ。小さな表（3〜4行）を文章で表現すること。4択。"),
        ("場合の数",         "順列・組み合わせに関するSPIらしい問題を1問作れ。4択。"),
        ("整数・数列",       "規則性のある数列や整数の性質に関するSPI問題を作れ。4択。"),
        ("平均・分散",       "平均・中央値・最頻値に関するSPI問題を作れ。4択。"),
        ("図形・空間",       "図形の面積・体積・角度に関するSPIらしい問題を作れ（図は文章で説明）。4択。"),
    ],
    "玉手箱": [
        ("四則逆算",   "□を含む式（□×n=m、n÷□=m、(□+n)×m=kなど）を作れ。選択肢は整数4択。複合式も含めること。"),
        ("長文一致",   "100〜150字の文章と、その内容についての命題を1つ作れ。選択肢は「A:一致する」「B:一致しない」「C:どちらとも言えない」の3択。"),
        ("テーブル計算","3〜4列・4〜5行の表（売上・在庫・人数等）を文章で与え、合計・差・割合などを問う問題を作れ。4択。"),
        ("図表読取",   "折れ線・棒グラフの数値を文章で表現し、増減・比較・割合を問う問題を作れ。4択。"),
        ("英語語彙",   "TOEIC600〜700点レベルの英単語の意味を問う4択問題を作れ。"),
        ("英文読解",   "3〜4文の短い英文を与え、内容に一致するものを4択で選ばせる問題を作れ。"),
        ("数列完成",   "空欄のある数列（等差・等比・フィボナッチ変形など）の□を埋める問題を作れ。4択。"),
    ],
    "英語": [
        ("語彙",       "TOEIC700点レベルの英単語・熟語の意味を4択で問う問題を作れ。"),
        ("文法",       "英文の空欄に入る最適な語（品詞・前置詞・接続詞等）を4択で選ぶ問題を作れ。"),
        ("読解",       "5〜6文の英文パッセージを書き、内容に関する設問（正誤・主題等）を4択で作れ。"),
        ("語句整序",   "英文の語句を並べ替える問題を作れ。答えは4パターン（A/B/C/D）の並び順。"),
    ],
}

_SPI_LLM_WORDS_LANGUAGE = [
    "逡巡","忖度","蓋然性","漸進","恣意","瑣末","截然","逼迫","敷衍","僭越",
    "矜持","跋扈","遁走","杜撰","慇懃","倦怠","齟齬","乖離","惹起","帰趨",
    "嚆矢","濫觴","淘汰","頑迷","慄然","慄く","邂逅","慷慨","諮問","訓示",
]

def _spi_generate_llm(filter_cat: str | None = None) -> dict | None:
    """LLMでSPI/玉手箱問題を動的生成する。失敗時はNone。"""
    o = _get_ollama()
    if o is None:
        return None

    # カテゴリと出題タイプをランダム選択
    cat = filter_cat if filter_cat else _random.choice(["言語", "非言語", "玉手箱", "英語"])
    subtypes = _SPI_LLM_SUBTYPES.get(cat, _SPI_LLM_SUBTYPES["言語"])
    sub, instruction = _random.choice(subtypes)

    # 言語系は語彙をランダムに差し込む
    word = _random.choice(_SPI_LLM_WORDS_LANGUAGE)
    instruction = instruction.replace("{word}", word)

    sys_prompt = (
        "あなたはSPI・玉手箱の問題作成専門家です。\n"
        "以下の指示に従い、問題を1問だけJSON形式で出力してください。\n"
        "出力形式（必ずこの形式のみ。説明・前置き不要）:\n"
        "{\n"
        '  "q": "問題文（改行は\\nで表現）",\n'
        '  "choices": ["A: 選択肢1", "B: 選択肢2", "C: 選択肢3", "D: 選択肢4"],\n'
        '  "ans": "A",\n'
        '  "exp": "解説文（正解の理由を1〜2文で）"\n'
        "}\n"
        "制約:\n"
        "- 選択肢は必ずA/B/C/Dの4つ（長文一致のみA/B/Cの3つでよい）\n"
        "- 正解は必ず1つ、他は明確に間違い\n"
        "- 数値問題は計算を確認してから出力すること\n"
        "- JSONのみ出力。```json等のマークダウン不要\n"
    )
    user_prompt = f"【カテゴリ】{cat}・{sub}\n【出題指示】{instruction}"

    try:
        raw = ""
        stream = o.chat(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user",   "content": user_prompt},
            ],
            stream=True,
            options={"temperature": 0.85, "num_predict": 600, "num_ctx": 1024},
        )
        deadline = time.time() + 15.0
        for chunk in stream:
            if time.time() > deadline:
                break
            raw += chunk.get("message", {}).get("content", "")
        # JSONを抽出
        m = re.search(r'\{[\s\S]*\}', raw)
        if not m:
            return None
        data = json.loads(m.group(0))
        # 必須フィールド検証
        if not all(k in data for k in ("q", "choices", "ans", "exp")):
            return None
        if len(data["choices"]) < 3:
            return None
        # 正解が選択肢に含まれているか
        ans = data["ans"].strip().upper()
        if not any(c.startswith(f"{ans}:") for c in data["choices"]):
            return None
        return {
            "cat": cat,
            "sub": f"{sub}★",   # ★=LLM生成を示すマーク
            "q":   data["q"],
            "choices": data["choices"],
            "ans": ans,
            "exp": data["exp"],
        }
    except Exception as e:
        print(f"{C['y']}[SPI-LLM] 生成失敗: {e}{C['w']}")
        return None

def _spi_pick_smart(filter_cat: str | None = None, use_llm: bool = True) -> dict:
    """
    LLM生成を優先し、失敗時はDBからローテーション出題する。
    LLMはバックグラウンドで呼び出し、タイムアウト付き。
    """
    if use_llm:
        result_box: list = []
        def _gen():
            q = _spi_generate_llm(filter_cat)
            if q:
                result_box.append(q)
        t = threading.Thread(target=_gen, daemon=True)
        t.start()
        t.join(timeout=5)   # 最大14秒待つ
        if result_box:
            _spi_mark_used(result_box[0])
            return result_box[0]
    # フォールバック: DBからローテーション
    return _spi_pick_fresh(filter_cat)

def _spi_format_q(q: dict, num: int | None = None) -> str:
    prefix = f"[問{num}] " if num else ""
    header = f"{C['c']}{prefix}【{q['cat']}・{q['sub']}】{C['w']}"
    body   = q["q"]
    choices = "\n".join(q["choices"])
    ans_hint = "A/B/C" if q.get("sub") == "長文一致" else "A/B/C/D"
    return f"{header}\n{body}\n{choices}\n{C['dim']}→ {ans_hint} で答えてください{C['w']}"

def _spi_feedback(q: dict, user_ans: str) -> str:
    """正誤判定＋選択肢付き解説を返す。"""
    correct = user_ans.upper() == q["ans"]
    # 正解の選択肢テキストを取得
    ans_letter = q["ans"]
    ans_text = next((c for c in q["choices"] if c.startswith(f"{ans_letter}:")), ans_letter)
    if correct:
        mark = f"{C['g']}✓ 正解！{C['w']}"
        detail = f"{C['g']}{ans_text}{C['w']}"
    else:
        mark = f"{C['r']}✗ 不正解  あなたの答え: {user_ans.upper()}{C['w']}"
        detail = f"{C['r']}正解 → {ans_text}{C['w']}"
    exp_block = f"{C['c']}【解説】{C['w']} {q['exp']}"
    return correct, f"{mark}\n{detail}\n{exp_block}"

def handle_spi(arg: str) -> str:
    arg = arg.strip()
    _sess = _spi_load_session()
    _spi_current  = _sess["current"]
    _spi_mock_queue   = _sess["mock_queue"]
    _spi_mock_results = _sess["mock_results"]
    _is_mock = _sess.get("is_mock", False)

    # ---------- 答え入力（A/B/C/D） ----------
    if arg.upper() in ("A", "B", "C", "D"):
        # 長文一致は3択なのでDは受け付けない
        if arg.upper() == "D" and _spi_current.get("sub") == "長文一致":
            return f"{C['y']}この問題は A/B/C の3択です。{C['w']}"
        if _is_mock:
            # 模擬試験モード（キューが空でも最終問題として処理）
            q = _spi_current
            if not q:
                return f"{C['y']}問題が出題されていません。/spi 模擬 で開始してください。{C['w']}"
            correct, fb = _spi_feedback(q, arg)
            _spi_record(q["cat"], correct)
            _spi_mock_results.append(correct)
            if _spi_mock_queue:
                _spi_current = _spi_mock_queue.pop(0)
                _spi_save_session(_spi_current, _spi_mock_queue, _spi_mock_results, is_mock=True)
                return f"{fb}\n\n{_spi_format_q(_spi_current, num=len(_spi_mock_results)+1)}"
            else:
                # 模擬試験終了
                total = len(_spi_mock_results)
                ok = sum(_spi_mock_results)
                _spi_save_session({}, [], [], is_mock=False)
                return (f"{fb}\n\n"
                        f"{C['c']}===== 模擬試験終了 ====={C['w']}\n"
                        f"結果: {ok}/{total} 問正解  ({ok*100//total}%)\n"
                        f"/spi 成績 で累計成績を確認できます。")
        else:
            # 通常1問モード
            q = _spi_current
            if not q:
                return f"{C['y']}問題が出題されていません。/spi で問題を出してください。{C['w']}"
            correct, fb = _spi_feedback(q, arg)
            _spi_record(q["cat"], correct)
            # ★[修正/spi-2] セッションクリアは feedback を返した後に確実に実行
            # 旧コードでは save_session({}) が返答前に走りタイミング依存の問題があった
            _spi_save_session({}, [], [], is_mock=False)
            return f"{fb}\n\n次の問題: /spi または /spi [言語/非言語/英語]"

    # ---------- 成績表示 ----------
    if arg in ("成績", "stats", "score"):
        sc = _spi_load_score()
        if sc["total"] == 0:
            return f"{C['y']}まだ解答がありません。/spi で問題を解いてみましょう。{C['w']}"
        pct = sc["correct"] * 100 // sc["total"]
        lines = [f"{C['c']}===== SPI成績 ====={C['w']}",
                 f"総合: {sc['correct']}/{sc['total']} 問正解  ({pct}%)"]
        for cat, v in sc.get("cats", {}).items():
            cpct = v["correct"]*100//v["total"] if v["total"] else 0
            bar = "█" * (cpct//10) + "░" * (10 - cpct//10)
            lines.append(f"  {cat}: {v['correct']}/{v['total']}  [{bar}] {cpct}%")
        return "\n".join(lines)

    # ---------- 成績リセット ----------
    if arg in ("リセット", "reset"):
        state = load_state()
        state.pop(_SPI_SCORE_KEY, None)
        save_state(state)
        _spi_clear_session()
        return f"{C['y']}成績をリセットしました。{C['w']}"

    # ---------- 模擬試験（10問連続） ----------
    if arg in ("模擬", "mock", "test"):
        # DB から5問 + LLMで5問生成（カテゴリ均等）
        cats_cycle = ["言語", "非言語", "玉手箱", "英語", "言語",
                      "非言語", "玉手箱", "英語", "言語", "非言語"]
        _random.shuffle(cats_cycle)
        pool_db = _random.sample(_SPI_DB, min(5, len(_SPI_DB)))
        pool: list[dict] = list(pool_db)  # まずDBの5問を追加

        print(f"{C['dim']}  模擬試験: LLMで問題生成中（5問）…{C['w']}", flush=True)
        for cat_hint in cats_cycle[5:]:   # 残り5問をLLM生成
            q_llm = _spi_generate_llm(cat_hint)
            if q_llm:
                pool.append(q_llm)
            else:
                pool.append(_spi_pick_fresh(cat_hint))  # 失敗時はDBフォールバック

        _random.shuffle(pool)
        pool = pool[:10]
        _spi_mock_queue = pool[1:]
        _spi_mock_results_new = []
        _spi_current = pool[0]
        _spi_save_session(_spi_current, _spi_mock_queue, _spi_mock_results_new, is_mock=True)
        llm_count = sum(1 for p in pool if "★" in p.get("sub", ""))
        return (f"{C['c']}===== 模擬試験開始（10問）====={C['w']}\n"
                f"内訳: DB {10-llm_count}問 + AI生成 {llm_count}問\n"
                f"A/B/C/D で答えてください。\n\n{_spi_format_q(_spi_current, num=1)}")

    # ---------- カテゴリ指定or通常出題 ----------
    cat_map = {"言語": "言語", "非言語": "非言語", "英語": "英語",
               "玉手箱": "玉手箱", "四則逆算": "玉手箱", "長文": "玉手箱", "テーブル": "玉手箱",
               "verbal": "言語", "math": "非言語", "english": "英語", "tama": "玉手箱"}
    filter_cat = cat_map.get(arg) if arg else None
    if arg and filter_cat is None:
        return (f"{C['r']}usage: /spi [言語|非言語|英語|玉手箱|模擬|成績|リセット]\n"
                f"または A/B/C/D で回答{C['w']}")
    with SystemSpinner("SPI問題を生成中…", stage="rag") as _sp:
        q = _spi_pick_smart(filter_cat, use_llm=True)
    _spi_save_session(q, [], [], is_mock=False)
    llm_tag = f" {C['dim']}[AI生成]{C['w']}" if "★" in q.get("sub", "") else ""
    return _spi_format_q(_spi_load_session()["current"]) + llm_tag

# ===== ハンドラ関数群 =====
def handle_memo(arg: str) -> str:
    state = load_state(); memos = state.setdefault("memo", [])
    sub, _, rest = arg.partition(" "); sub = sub.lower().strip(); rest = rest.strip()
    if not arg or sub == "list":
        if not memos: return f"{C['y']}メモは空です。{C['w']}"
        return f"{C['c']}=== MEMORY ==={C['w']}\n" + "\n".join(f"{i+1}. {m.get('text','')} ({m.get('time','')})" for i, m in enumerate(memos[-20:]))
    if sub == "add":
        if not rest: return f"{C['r']}usage: /m add <内容>{C['w']}"
        memos.append({"time": now_stamp(), "text": rest}); save_state(state); update_keyword_memory(rest); vector_add(rest)
        return f"{C['g']}覚えました: {rest}{C['w']}"
    if sub == "find":
        if not rest: return f"{C['r']}usage: /m find <検索語>{C['w']}"
        hits = [(i, m) for i, m in enumerate(memos, 1) if rest.lower() in m.get("text", "").lower()]
        if not hits: return f"{C['y']}該当なし。{C['w']}"
        return f"{C['c']}=== HIT ==={C['w']}\n" + "\n".join(f"{i}. {m.get('text','')} ({m.get('time','')})" for i, m in hits)
    if sub == "del":
        if not rest.isdigit(): return f"{C['r']}usage: /m del <番号>{C['w']}"
        idx = int(rest) - 1
        if idx < 0 or idx >= len(memos): return f"{C['r']}その番号はありません。{C['w']}"
        removed = memos.pop(idx); save_state(state)
        return f"{C['y']}削除: {removed.get('text','')}{C['w']}"
    return f"{C['r']}usage: /m add/list/find/del{C['w']}"

def handle_dict(arg: str) -> str:
    state = load_state(); entries = state.setdefault("dict", [])
    sub, _, rest = arg.partition(" "); sub = sub.strip().lower(); rest = rest.strip()
    if not arg or sub == "list":
        if not entries: return f"{C['y']}辞書は空です。{C['w']}"
        return f"{C['c']}=== 辞書一覧 ==={C['w']}\n" + "\n".join(f"{i+1}. {e['term']}: {e.get('def','')[:60]}" for i, e in enumerate(entries[-40:]))
    if sub == "add":
        if "|" not in rest: return f"{C['r']}usage: /dict add <用語> | <説明>{C['w']}"
        term, _, defn = rest.partition("|"); term = term.strip(); defn = defn.strip()
        if not term or not defn: return f"{C['r']}usage: /dict add <用語> | <説明>{C['w']}"
        entries.append({"term": term, "def": defn, "time": now_stamp()})
        save_state(state); vector_add(f"{term}: {defn}", {"type": "dict", "term": term})
        return f"{C['g']}辞書に追加: {term}{C['w']}"
    if sub == "del":
        if not rest: return f"{C['r']}usage: /dict del <用語>{C['w']}"
        for i, e in enumerate(entries):
            if e["term"] == rest: removed = entries.pop(i); save_state(state); return f"{C['y']}削除: {removed['term']}{C['w']}"
        return f"{C['r']}「{rest}」は見つかりません{C['w']}"
    if sub == "find":
        if not rest: return f"{C['r']}usage: /dict find <キーワード>{C['w']}"
        hits = [(i, e) for i, e in enumerate(entries, 1) if rest.lower() in e["term"].lower() or rest.lower() in e["def"].lower()]
        if not hits: return f"{C['y']}該当なし。{C['w']}"
        return f"{C['c']}=== 辞書検索: {rest} ==={C['w']}\n" + "\n".join(f"{i}. {e['term']}: {e.get('def','')[:80]}" for i, e in hits)
    for e in entries:
        if e["term"].lower() == sub: return f"{C['c']}【{e['term']}】{C['w']}{e['def']} ({e.get('time','')})"
    hits = [e for e in entries if sub in e["term"].lower()]
    if hits: return f"{C['c']}=== 部分一致 ==={C['w']}\n" + "\n".join(f"  {e['term']}: {e.get('def','')[:80]}" for e in hits[:5])
    return f"{C['r']}「{sub}」は辞書にありません。/dict add <用語> | <説明> で追加できます。{C['w']}"

def dict_context(text: str) -> str:
    if not text: return ""
    state = load_state(); entries = state.get("dict", [])
    if not entries: return ""
    text_lower = text.lower()
    matches = [f"  【辞書】{e['term']}: {e.get('def','')}" for e in entries if e.get("term","").lower() in text_lower]
    if not matches:
        matches = [f"  【関連辞書】{r}" for r in vector_search(text, n=3) if r and ":" in r and len(r) < 200]
    return "\n" + "\n".join(matches[:3]) if matches else ""

def handle_doc(arg: str) -> str:
    state = load_state(); docs = state.setdefault("docs", [])
    sub, _, rest = arg.partition(" "); sub = sub.strip().lower(); rest = rest.strip()
    if not arg or sub == "list":
        if not docs: return f"{C['y']}文書は空です。{C['w']}"
        return f"{C['c']}=== 保存文書 ==={C['w']}\n" + "\n".join(f"{i+1}. {d['title']} ({len(d['text'])}字)" for i, d in enumerate(docs[-20:]))
    if sub == "add":
        if "|" not in rest: return f"{C['r']}usage: /doc add <タイトル> | <本文>{C['w']}"
        title, _, text = rest.partition("|"); title = title.strip(); text = text.strip()
        if not title or not text: return f"{C['r']}usage: /doc add <タイトル> | <本文>{C['w']}"
        docs.append({"title": title, "text": text, "time": now_stamp()})
        save_state(state); vector_add(f"[{title}] {text[:300]}", {"type": "doc", "title": title})
        return f"{C['g']}文書保存: {title} ({len(text)}字){C['w']}"
    if sub == "show":
        if not rest: return f"{C['r']}usage: /doc show <タイトル>{C['w']}"
        for d in docs:
            if d["title"].lower() == rest.lower(): return f"{C['c']}=== {d['title']} ==={C['w']}\n{d['text']}"
        return f"{C['r']}「{rest}」は見つかりません{C['w']}"
    if sub == "think": return "__THINK__" + rest
    if sub == "del":
        if not rest: return f"{C['r']}usage: /doc del <タイトル>{C['w']}"
        for i, d in enumerate(docs):
            if d["title"] == rest: removed = docs.pop(i); save_state(state); return f"{C['y']}削除: {removed['title']}{C['w']}"
        return f"{C['r']}「{rest}」は見つかりません{C['w']}"
    for d in docs:
        if d["title"].lower() == sub: return f"{C['c']}=== {d['title']} ==={C['w']}\n{d['text'][:500]}"
    return f"{C['r']}usage: /doc add/list/show/think/del{C['w']}"

def format_quests() -> str:
    quests = load_state().get("quests", [])
    if not quests: return f"{C['y']}クエストは空です。{C['w']}"
    return f"{C['c']}=== QUEST LOG ==={C['w']}\n" + "\n".join(f"{i}. [{'DONE' if q.get('done') else 'OPEN'}] {q.get('goal','')} ({q.get('time','')})" for i, q in enumerate(quests[-15:], 1))

def complete_quest(arg: str) -> str:
    state = load_state(); quests = state.get("quests", [])
    if not arg.isdigit(): return f"{C['r']}usage: /q done <番号>{C['w']}"
    idx = int(arg) - 1
    if idx < 0 or idx >= len(quests): return f"{C['r']}その番号はありません。{C['w']}"
    quests[idx]["done"] = True; quests[idx]["done_time"] = now_stamp(); save_state(state)
    return f"{C['g']}完了: {quests[idx].get('goal','')}{C['w']}"

def show_quest(arg: str) -> str:
    quests = load_state().get("quests", [])
    if not arg.isdigit(): return f"{C['r']}usage: /q show <番号>{C['w']}"
    idx = int(arg) - 1
    if idx < 0 or idx >= len(quests): return f"{C['r']}その番号はありません。{C['w']}"
    q = quests[idx]
    return f"{C['c']}=== QUEST #{idx+1} [{'DONE' if q.get('done') else 'OPEN'}] ==={C['w']}\n{q.get('plan','')}"

def save_quest(goal: str, plan: str) -> None:
    state = load_state(); quests = state.setdefault("quests", [])
    quests.append({"time": now_stamp(), "goal": goal, "plan": plan, "done": False}); save_state(state)

def debug_report() -> str:
    rows = [f"{C['c']}=== S-01 DEBUG v128.1 ==={C['w']}"]
    rows.append(f"RAGキャッシュ: {len(RAG_CACHE)}")
    if RAG_CACHE:
        for key, (ts, val, acc, conf) in list(RAG_CACHE.items())[-5:]:
            rows.append(f"  [{key[:20]}] age={int(time.time()-ts)}s len={len(val)} acc={acc} conf={conf:.1f}")
    rows.append(f"キーワード: {', '.join(KEYWORD_MEMORY) or 'なし'}")
    rows.append(f"モデル: {MODEL_NAME} | パワー: {POWER_MODE}")
    return "\n".join(rows)

def doctor_report() -> str:
    return "\n".join([
        f"{C['c']}=== S-01 DOCTOR v128.1 ==={C['w']}", f"python: {sys.version.split()[0]}",
        f"platform: {platform.system()} {platform.release()}", f"model: {MODEL_NAME}",
        f"power: {POWER_MODE}", f"ollama: {'OK' if _get_ollama() is not None else 'NG'}",
        f"yt-dlp: {'OK' if shutil.which('yt-dlp') else 'NG'}", f"mpv: {'OK' if shutil.which('mpv') else 'NG'}",
        f"RAG cache: {len(RAG_CACHE)}", f"kw mem: {len(KEYWORD_MEMORY)}",
    ])

def set_power_mode(arg: str) -> str:
    global POWER_MODE
    mode = arg.strip().lower()
    if not mode: return f"{C['c']}current: {POWER_MODE}{C['w']}"
    if mode not in ("low", "mid", "high", "ultra"): return f"{C['r']}usage: /power low|mid|high|ultra{C['w']}"
    POWER_MODE = mode
    return f"{C['g']}power: {POWER_MODE} ({'軽量' if mode=='low' else '標準' if mode=='mid' else '高推論' if mode=='high' else '最大推論'}){C['w']}"

def build_custom_persona(attr: str, hint: str = "") -> dict:
    name = attr.strip()[:40] or "CUSTOM"
    # ★[修正1] ヒントなしの場合はキャッシュを先に確認してWeb/LLM処理を完全スキップ
    if not hint and name in PERSONA_STYLE_CACHE:
        return PERSONA_STYLE_CACHE[name]
    if hint:
        style = f"{name}。{hint}"
        fp_match = re.search(r'一人称(?:は)?[「『]?([ぁ-んァ-ヶ一-龯]{1,4})', style)
        return {"name": name, "style": style[:250], "first_person": fp_match.group(1) if fp_match else "私"}
    ARCHETYPES = {
        "お嬢様": {"style": "上品な言葉遣い。わたくし口調。丁寧で格式高い", "fp": "わたくし"},
        "ギャル": {"style": "明るいギャル口調。テンション高め。語尾に「っ」「じゃん」", "fp": "あたし"},
        "ツンデレ": {"style": "最初はつっけんどんだが徐々に甘える", "fp": "私"},
        "クール": {"style": "冷静で淡々とした口調。感情を抑えめ", "fp": "私"},
        "無口": {"style": "言葉数が少ない。一言二言で簡潔に", "fp": "私"},
        "元気": {"style": "明るく活発な口調。感嘆符多用", "fp": "私"},
        "大人": {"style": "落ち着いた大人の口調。知的で余裕がある", "fp": "私"},
        "子供": {"style": "子供らしい無邪気な口調。単純で素直", "fp": "ボク"},
        "男性": {"style": "男らしい口調。さっぱりとした物言い", "fp": "俺"},
        "女性": {"style": "女性らしい柔らかい口調。丁寧で優しい", "fp": "私"},
        "魔王": {"style": "威厳のある高圧的な口調", "fp": "朕"},
        "勇者": {"style": "正義感のある熱い口調", "fp": "俺"},
        "執事": {"style": "丁寧な敬語。主君に仕える忠実な口調", "fp": "私"},
        "メイド": {"style": "丁寧で献身的な口調。ご主人様呼び", "fp": "私"},
        "忍者": {"style": "簡潔で謎めいた口調。〜でござる", "fp": "拙者"},
        "中二病": {"style": "厨二病的な中二病全開の口調", "fp": "僕"},
        "先生": {"style": "教師らしい丁寧な口調。時にお説教的", "fp": "私"},
        "猫": {"style": "猫のような気ままな口調。〜にゃ", "fp": "私"},
        "先輩": {"style": "少し先輩風を吹かせる口調。面倒見が良い", "fp": "私"},
        "後輩": {"style": "礼儀正しい後輩口調。年上を敬う", "fp": "私"},
    }
    parts = re.split(r'[\s　、,・]', name)
    styles = []; first_person = "私"; matched = False
    for part in parts:
        part_lower = part.lower().strip()
        if part_lower in ARCHETYPES:
            arch = ARCHETYPES[part_lower]; styles.append(arch["style"]); first_person = arch["fp"]; matched = True
    if not matched:
        return _llm_persona_style(name)
    return {"name": name, "style": (f"{name}。{' + '.join(styles)}")[:250], "first_person": first_person}

PERSONA_STYLE_CACHE: dict[str, dict] = {}

def _fetch_persona_web_info(name: str) -> str:
    """複数ソースを並列スクレイピングしてペルソナ情報を収集する。
    歌詞検索と同じ手法: Wikipedia + DDG + Yahoo + Bing + コトバンク + SEP(哲学者向け) を同時取得し
    重複除去・スコアリングで最良テキストを返す。"""
    if OFFLINE_MODE: return ""

    res: dict[str, str] = {}
    lock = threading.Lock()

    def _run(key: str, fn, *args):
        try:
            val = fn(*args)
            with lock:
                res[key] = (val or "").strip()
        except Exception as _e:
            print(f"{C['y']}[WARN] RAG並列取得失敗 [{key}]: {_e}{C['w']}")

    # SEP (Stanford Encyclopedia of Philosophy) スクレイピング
    def _fetch_sep(name: str) -> str:
        try:
            slug = name.lower().replace(" ", "-").replace("・", "-").replace("　", "-")
            # よく使われる英語名マッピング
            slug_map = {
                "ソクラテス": "socrates", "プラトン": "plato", "アリストテレス": "aristotle",
                "エピクテトス": "epictetus", "マルクス・アウレリウス": "marcus-aurelius",
                "トマス・アクィナス": "aquinas", "デカルト": "descartes", "スピノザ": "spinoza",
                "ライプニッツ": "leibniz", "ロック": "locke", "ヒューム": "hume",
                "カント": "kant", "ヘーゲル": "hegel", "ショーペンハウアー": "schopenhauer",
                "ミル": "mill", "ニーチェ": "nietzsche",
                "ウィリアム・ジェームズ": "james", "フッサール": "husserl",
                "ハイデガー": "heidegger", "サルトル": "sartre",
                "ボーヴォワール": "beauvoir", "ラッセル": "russell",
                "前期ウィトゲンシュタイン": "wittgenstein", "後期ウィトゲンシュタイン": "wittgenstein",
                "ウィトゲンシュタイン": "wittgenstein",
            }
            sep_slug = slug_map.get(name, slug)
            url = f"https://plato.stanford.edu/entries/{sep_slug}/"
            h = fetch_html(url, timeout=5, silent=True, spoof_bot=True)
            if not h or len(h) < 500: return ""
            # preamble div を抽出
            m = re.search(r'<div id="preamble"[^>]*>(.*?)</div>', h, re.S | re.I)
            if not m:
                m = re.search(r'<div[^>]+class="[^"]*toc[^"]*"[^>]*>.*?</div>(.*?)<div', h, re.S | re.I)
            if m:
                text = strip_tags(m.group(1))
                lines = [l.strip() for l in text.splitlines() if len(l.strip()) > 30]
                return "[SEP] " + " / ".join(lines[:4])
        except Exception as _e:
            print(f"{C['y']}[WARN] SEP取得失敗: {_e}{C['w']}")
        return ""

    # ブリタニカ日本語版
    def _fetch_britannica_ja(name: str) -> str:
        try:
            url = f"https://britannica.co.jp/search/?q={U.quote(name)}"
            h = fetch_html(url, timeout=4, silent=True, spoof_bot=True)
            snips = re.findall(r'<p[^>]*class="[^"]*summary[^"]*"[^>]*>(.*?)</p>', h, re.S | re.I)
            if not snips:
                snips = re.findall(r'<div[^>]*class="[^"]*description[^"]*"[^>]*>(.*?)</div>', h, re.S | re.I)
            lines = [strip_tags(s).strip() for s in snips[:3] if len(strip_tags(s).strip()) > 20]
            return "\n".join(f"[ブリタニカ] {l}" for l in lines)
        except Exception:
            return ""

    tasks = [
        ("wiki",       get_wikipedia,          name),
        ("wiki_en",    get_wikipedia,          name + " philosopher"),  # 英語Wikipedia
        ("ddg",        _fetch_ddg_snippets,    name + " 哲学者 思想 特徴 口調"),
        ("ddg2",       _fetch_ddg_snippets,    name + " philosophy biography"),
        ("yahoo",      _fetch_yahoo_snippets,  name + " 哲学 性格 言動 思想"),
        ("bing",       _fetch_bing_snippets,   name + " 哲学者 人物"),
        ("kotobank",   _fetch_kotobank,        name),
        ("sep",        _fetch_sep,             name),
        ("britannica", _fetch_britannica_ja,   name),
    ]
    threads = [
        threading.Thread(target=_run, args=(k, fn, *a), daemon=True)
        for k, fn, *a in tasks
    ]
    for t in threads: t.start()

    # Wikiが先に来ればそこで早期終了、なければ全ソース待つ
    deadline = time.time() + RAG_TIMEOUT + 2.0
    while time.time() < deadline:
        with lock:
            wiki_ok = len(res.get("wiki", "")) > 100
            web_ok  = sum(len(res.get(k, "")) for k in ["ddg", "yahoo", "bing", "kotobank", "sep"]) > 400
            if wiki_ok and web_ok: break
        time.sleep(0.15)
    for t in threads: t.join(timeout=0.5)

    with lock:
        all_res = dict(res)

    # ── 結果のマージ・重複除去 ──────────────────────────────────────
    parts = []

    # Wikipedia (日本語優先、なければ英語)
    wiki_ja = all_res.get("wiki", "")
    wiki_en = all_res.get("wiki_en", "")
    if wiki_ja and len(wiki_ja) > 100:
        parts.append(f"[Wikipedia JA]\n{wiki_ja[:2000]}")
    elif wiki_en and len(wiki_en) > 100:
        parts.append(f"[Wikipedia EN]\n{wiki_en[:1500]}")

    # SEP (Stanford)
    sep_text = all_res.get("sep", "")
    if sep_text:
        parts.append(sep_text[:600])

    # ブリタニカ
    bri_text = all_res.get("britannica", "")
    if bri_text:
        parts.append(bri_text[:400])

    # コトバンク
    ktb_text = all_res.get("kotobank", "")
    if ktb_text:
        parts.append(ktb_text[:400])

    # 検索スニペット群 (DDG・Yahoo・Bing) を重複除去してマージ
    snippet_lines = []
    for key in ["ddg", "ddg2", "yahoo", "bing"]:
        block = all_res.get(key, "")
        if block:
            snippet_lines.extend(block.splitlines())
    deduped = _deduplicate_lines(snippet_lines)
    if deduped:
        parts.append(f"[Web検索スニペット]\n" + "\n".join(deduped[:12]))

    final = "\n\n".join(p for p in parts if p.strip())
    n_sources = sum(1 for k in ["wiki", "sep", "britannica", "kotobank", "ddg", "yahoo", "bing"] if all_res.get(k, ""))
    print(f"{C['dim']}[ペルソナWeb] {name}: {n_sources}ソース取得 / {len(final)}字{C['w']}", flush=True)
    return final

def _llm_persona_style(name: str) -> dict:
    if name in PERSONA_STYLE_CACHE:
        return PERSONA_STYLE_CACHE[name]
    o = _get_ollama()

    # ── ① ネットから人物情報を取得 ──────────────────────────────
    web_info = ""
    with SystemSpinner(f"Web検索: {name}", stage="rag"):
        web_info = _fetch_persona_web_info(name)

    # ── ② LLMでペルソナを生成（情報があれば注入） ────────────────
    if o is None:
        # Ollamaなし：Webテキストからルールベースで推定
        style = f"『{name}』らしい口調。"
        if web_info:
            style += web_info[:200]
        p = {"name": name, "style": style[:250], "first_person": "私", "_web": bool(web_info)}
        PERSONA_STYLE_CACHE[name] = p
        return p

    result = [""]
    def _gen():
        try:
            if web_info:
                prompt = (
                    f"以下は「{name}」に関する複数ソース（Wikipedia・SEP・ブリタニカ・Web検索）からの情報だ:\n"
                    f"{web_info[:1800]}\n\n"
                    f"この情報を踏まえ、「{name}」がAIとして日本語で話すときの"
                    f"口調・性格・思想的特徴・一人称を80字以内で設定せよ。"
                    f"形式：「一人称:XX / 口調:YYYY / 特徴:ZZZZ」"
                )
            else:
                prompt = (
                    f"「{name}」がAIとして日本語で話すときの口調・性格・一人称を"
                    f"30字以内で設定せよ。形式：「一人称:XX / 口調:YYYY」"
                )
            r = o.chat(
                model=MODEL_NAME,
                messages=[{"role": "user", "content": prompt}],
                options={"num_predict": 120, "temperature": 0.3},
                stream=False
            )
            result[0] = r["message"]["content"].strip()
        except Exception as _e:
            print(f"{C['y']}[WARN] LLM生成スレッド失敗: {_e}{C['w']}")

    t = threading.Thread(target=_gen, daemon=True)
    t.start(); t.join(timeout=5.0)

    raw_style = result[0]
    if not raw_style or len(raw_style) < 8:
        raw_style = f"『{name}』らしい口調。一人称は「私」。"

    # 一人称を抽出
    fp = "私"
    m = re.search(r'一人称[：:は「『]?\s*([ぁ-んァ-ヶ一-龯a-zA-Z]{1,6})', raw_style)
    if m:
        fp = m.group(1).strip()

    # スタイル文字列を構築（Web情報の要約を冒頭に付与）
    style_parts = [raw_style[:300]]
    if web_info:
        # Wikiの先頭2〜3文 + SEP/ブリタニカの要点をヒントとして付加
        first_lines = [l.strip() for l in web_info.splitlines() if len(l.strip()) > 25][:3]
        if first_lines:
            style_parts.append("【参照】" + " / ".join(first_lines)[:250])

    final_style = "\n".join(style_parts)[:600]
    p = {"name": name, "style": final_style, "first_person": fp, "_web": bool(web_info)}
    PERSONA_STYLE_CACHE[name] = p
    print(f"{C['dim']}[ペルソナ生成] {name} / 一人称:{fp} / Web情報:{'あり' if web_info else 'なし'}{C['w']}")
    return p

def _model_name(m) -> str:
    if isinstance(m, dict): return m.get("name") or m.get("model") or ""
    return getattr(m, "name", "") or getattr(m, "model", "") or ""

def check_ollama_connection() -> bool:
    o = _get_ollama()
    if o is None: print(f"{C['r']}[FATAL] ollama not installed. pip install ollama{C['w']}"); return False
    try:
        models = o.list()
        items = models.get("models", []) if isinstance(models, dict) else getattr(models, "models", [])
        names = [_model_name(m) for m in items]
        found = any(MODEL_NAME in n or n.startswith(MODEL_NAME.split(":")[0]) for n in names)
        if not found: print(f"{C['y']}model '{MODEL_NAME}' not found. available: {', '.join(names) or 'none'}{C['w']}"); return False
        return True
    except Exception as e: print(f"{C['r']}[FATAL] Ollama connection failed: {e}{C['w']}"); return False

def start_roleplay(scene: str, per_id: int) -> None:
    global ROLEPLAY_ACTIVE, ROLEPLAY_SCENE
    ROLEPLAY_ACTIVE, ROLEPLAY_SCENE = True, scene
    print(f"{C['p']}[RP開始: {get_persona(per_id)['name']} / 終了は /rend]{C['w']}")

def end_roleplay() -> None:
    global ROLEPLAY_ACTIVE, ROLEPLAY_SCENE
    ROLEPLAY_ACTIVE, ROLEPLAY_SCENE = False, ""
    print(f"{C['y']}[ロールプレイ終了]{C['w']}")

def handle_ety(word: str) -> str:
    """Etymology 図鑑: 英単語を語根・接頭辞・接尾辞に分解して色分け表示する。"""
    word = word.strip().lower()
    if not word:
        return (
            f"{C['r']}usage: /ety <英単語>{C['w']}\n"
            f"  例: /ety impossible  →  im-(否定) + poss(置く) + -ible(できる)"
        )

    TYPE_COLOR = {"prefix": C['b'], "root": C['y'], "suffix": C['g']}
    TYPE_LABEL = {"prefix": "接頭辞", "root": "語根  ", "suffix": "接尾辞"}


    # ── 語根辞書（AI誤解釈を補正するポスト補正用） ──
    _MDICT: dict[str, tuple | None] = {
        # よく誤解される語根（英単語と同形だが別意味）
        "par":     ("root",   "現れる・見える",      "appear, show",         "Latin parere"),
        "parent":  ("root",   "現れる・見える",      "appear (not 'father')", "Latin parere"),
        "port":    ("root",   "運ぶ",               "carry, bear",          "Latin portare"),
        "man":     ("root",   "手",                 "hand",                 "Latin manus"),
        "manu":    ("root",   "手",                 "hand",                 "Latin manus"),
        "ant":     ("suffix", "〜な（形容詞）",      "forming adjectives",   "Latin"),
        "rupt":    ("root",   "破る",               "break, burst",         "Latin rumpere"),
        "spect":   ("root",   "見る",               "look, see",            "Latin spectare"),
        "spec":    ("root",   "見る",               "look, see",            "Latin spectare"),
        "vert":    ("root",   "回す・向ける",        "turn",                 "Latin vertere"),
        "vers":    ("root",   "回す・向ける",        "turn",                 "Latin vertere"),
        "duct":    ("root",   "導く",               "lead",                 "Latin ducere"),
        "duc":     ("root",   "導く",               "lead",                 "Latin ducere"),
        "mit":     ("root",   "送る",               "send",                 "Latin mittere"),
        "miss":    ("root",   "送る",               "send",                 "Latin mittere"),
        "dict":    ("root",   "言う",               "say, speak",           "Latin dicere"),
        "vis":     ("root",   "見る",               "see",                  "Latin videre"),
        "vid":     ("root",   "見る",               "see",                  "Latin videre"),
        "cap":     ("root",   "取る",               "take, seize",          "Latin capere"),
        "ced":     ("root",   "行く・譲る",          "go, yield",            "Latin cedere"),
        "ceed":    ("root",   "行く・進む",          "go, proceed",          "Latin cedere"),
        "cess":    ("root",   "行く・止まる",        "go, stop",             "Latin cedere"),
        "fac":     ("root",   "作る・する",          "make, do",             "Latin facere"),
        "fact":    ("root",   "作る・する",          "make, do",             "Latin facere"),
        "fect":    ("root",   "作る・する",          "make, do",             "Latin facere"),
        "fer":     ("root",   "運ぶ",               "carry, bear",          "Latin ferre"),
        "ject":    ("root",   "投げる",             "throw",                "Latin jacere"),
        "jac":     ("root",   "投げる",             "throw",                "Latin jacere"),
        "luc":     ("root",   "光",                 "light",                "Latin lux"),
        "lum":     ("root",   "光",                 "light",                "Latin lumen"),
        "mob":     ("root",   "動く",               "move",                 "Latin movere"),
        "mot":     ("root",   "動く",               "move",                 "Latin movere"),
        "mov":     ("root",   "動く",               "move",                 "Latin movere"),
        "neg":     ("root",   "否定する",           "deny, negate",         "Latin negare"),
        "pend":    ("root",   "吊るす・支払う",      "hang, pay",            "Latin pendere"),
        "pens":    ("root",   "吊るす・支払う",      "hang, pay",            "Latin pendere"),
        "pon":     ("root",   "置く",               "place, put",           "Latin ponere"),
        "pos":     ("root",   "置く",               "place, put",           "Latin ponere"),
        "poss":    ("root",   "置く・できる",        "place, be able",       "Latin ponere/posse"),
        "scrib":   ("root",   "書く",               "write",                "Latin scribere"),
        "script":  ("root",   "書く",               "write",                "Latin scribere"),
        "sent":    ("root",   "感じる",             "feel, sense",          "Latin sentire"),
        "sens":    ("root",   "感じる",             "feel, sense",          "Latin sentire"),
        "sist":    ("root",   "立つ",               "stand",                "Latin sistere"),
        "stat":    ("root",   "立つ・状態",          "stand, state",         "Latin stare"),
        "struct":  ("root",   "建てる",             "build",                "Latin struere"),
        "tang":    ("root",   "触れる",             "touch",                "Latin tangere"),
        "tact":    ("root",   "触れる",             "touch",                "Latin tangere"),
        "tract":   ("root",   "引く",               "pull, draw",           "Latin trahere"),
        "ten":     ("root",   "保つ・持つ",          "hold, keep",           "Latin tenere"),
        "tend":    ("root",   "伸ばす・向かう",      "stretch, tend",        "Latin tendere"),
        "tens":    ("root",   "伸ばす・張る",        "stretch, strain",      "Latin tendere"),
        "tent":    ("root",   "伸ばす・試みる",      "stretch, attempt",     "Latin tendere"),
        "ext":     ("prefix", "外に伸ばす",          "outward extension",    "Latin ex+tendere"),
        "vit":     ("root",   "生命",               "life",                 "Latin vita"),
        "viv":     ("root",   "生きる",             "live",                 "Latin vivere"),
        "voc":     ("root",   "声・呼ぶ",           "voice, call",          "Latin vocare"),
        "val":     ("root",   "強い・価値",          "strong, worth",        "Latin valere"),
        "urb":     ("root",   "都市",               "city",                 "Latin urbs"),
        "terr":    ("root",   "土地",               "land, earth",          "Latin terra"),
        "tempor":  ("root",   "時間",               "time",                 "Latin tempus"),
        "sign":    ("root",   "印・意味",           "sign, mark",           "Latin signum"),
        "grad":    ("root",   "歩む・段階",          "step, degree",         "Latin gradus"),
        "corp":    ("root",   "体",                 "body",                 "Latin corpus"),
        "sanct":   ("root",   "神聖な",             "holy, sacred",         "Latin sanctus"),
        # Prefixes
        "trans":   ("prefix", "越えて・横切って",    "across, through",      "Latin"),
        "pre":     ("prefix", "前に",               "before",               "Latin"),
        "post":    ("prefix", "後に",               "after",                "Latin"),
        "sub":     ("prefix", "下に",               "under, below",         "Latin"),
        "super":   ("prefix", "上に",               "above, over",          "Latin"),
        "inter":   ("prefix", "間に",               "between",              "Latin"),
        "re":      ("prefix", "再び",               "again, back",          "Latin"),
        "ex":      ("prefix", "外に",               "out of",               "Latin"),
        "de":      ("prefix", "下に・離れて",        "down, away",           "Latin"),
        "com":     ("prefix", "共に",               "together, with",       "Latin"),
        "con":     ("prefix", "共に",               "together, with",       "Latin"),
        "pro":     ("prefix", "前に",               "forward, for",         "Latin/Greek"),
        "anti":    ("prefix", "反対",               "against",              "Greek"),
        "auto":    ("prefix", "自己",               "self",                 "Greek"),
        "tele":    ("prefix", "遠い",               "far, distant",         "Greek"),
        "hyper":   ("prefix", "過剰",               "over, excessive",      "Greek"),
        "hypo":    ("prefix", "不足",               "under, below",         "Greek"),
        "semi":    ("prefix", "半分",               "half",                 "Latin"),
        "dis":     ("prefix", "離れて・否定",        "apart, not",           "Latin"),
        "ab":      ("prefix", "離れて",             "away from",            "Latin"),
        "ad":      ("prefix", "〜へ向かって",        "toward",               "Latin"),
        "per":     ("prefix", "完全に・通して",      "through, thoroughly",  "Latin"),
        "in":      ("prefix", "中に・否定",          "in, into, not",        "Latin"),
        "im":      ("prefix", "中に・否定",          "in, not (before m/p)", "Latin"),
        "un":      ("prefix", "否定",               "not",                  "Old English"),
        "mis":     ("prefix", "誤って",             "wrongly",              "Old English"),
        # Suffixes
        "ent":     ("suffix", "〜な（形容詞）",      "forming adjectives",   "Latin"),
        "tion":    ("suffix", "〜すること（名詞）",  "forming nouns",        "Latin"),
        "sion":    ("suffix", "〜すること（名詞）",  "forming nouns",        "Latin"),
        "ment":    ("suffix", "〜すること（名詞）",  "forming nouns",        "Latin"),
        "ness":    ("suffix", "〜の状態（名詞）",    "state, quality",       "Old English"),
        "ity":     ("suffix", "〜の性質（名詞）",    "state, quality",       "Latin"),
        "ible":    ("suffix", "〜できる（形容詞）",  "able to be",           "Latin"),
        "able":    ("suffix", "〜できる（形容詞）",  "able to be",           "Latin"),
        "ive":     ("suffix", "〜的な（形容詞）",    "tending to",           "Latin"),
        "ous":     ("suffix", "〜に満ちた（形容詞）","full of, having",      "Latin"),
        "ful":     ("suffix", "〜に満ちた（形容詞）","full of",              "Old English"),
        "less":    ("suffix", "〜のない（形容詞）",  "without",              "Old English"),
        "er":      ("suffix", "〜する人（名詞）",    "one who does",         "Old English"),
        "or":      ("suffix", "〜する人（名詞）",    "one who does",         "Latin"),
        "ist":     ("suffix", "〜主義者（名詞）",    "one who does/believes","Greek"),
        "ism":     ("suffix", "〜主義（名詞）",      "doctrine, practice",   "Greek"),
        "ize":     ("suffix", "〜にする（動詞）",    "to make, to do",       "Greek"),
        "ify":     ("suffix", "〜にする（動詞）",    "to make",              "Latin"),
        "ly":      ("suffix", "〜的に（副詞）",      "in a manner",          "Old English"),
        "al":      ("suffix", "〜の（形容詞）",      "relating to",          "Latin"),
        "ic":      ("suffix", "〜の（形容詞）",      "relating to",          "Greek"),
        "logy":    ("suffix", "〜の学問",            "study of",             "Greek"),
        "ology":   ("suffix", "〜の学問",            "study of",             "Greek"),
        "ance":    ("suffix", "〜の状態（名詞）",    "state, quality",       "Latin"),
        "ence":    ("suffix", "〜の状態（名詞）",    "state, quality",       "Latin"),
        "ward":    ("suffix", "〜の方向へ",          "in the direction of",  "Old English"),
        "ship":    ("suffix", "〜の状態・関係",      "state, condition",     "Old English"),
    }

    # few-shot 例示（1bでも安定するよう簡潔化）
    FEW_SHOT_SYSTEM = (
        "Etymology expert. Output ONLY one JSON object, single line, no markdown, no explanation.\n"
        "CRITICAL: meaning_ja MUST be Japanese (日本語). NEVER output Chinese characters as meaning_ja.\n"
        'FORMAT: {"word":"W","pos":"P","morphemes":[{"text":"T","type":"root","meaning_ja":"M","meaning_en":"E","origin":"O"}],"combined_meaning_ja":"CM","etymology_note":"N"}\n'
        'EXAMPLE INPUT: biology\n'
        'EXAMPLE OUTPUT: {"word":"biology","pos":"noun","morphemes":['
        '{"text":"bio","type":"prefix","meaning_ja":"生命","meaning_en":"life","origin":"Greek bios"},'
        '{"text":"logy","type":"suffix","meaning_ja":"〜学","meaning_en":"study of","origin":"Greek -logia"}],'
        '"combined_meaning_ja":"生物学","etymology_note":"ギリシャ語 bios（生命）+ logia（学問）由来。"}\n'
        'EXAMPLE INPUT: extend\n'
        'EXAMPLE OUTPUT: {"word":"extend","pos":"verb","morphemes":['
        '{"text":"ex","type":"prefix","meaning_ja":"外へ","meaning_en":"out","origin":"Latin ex"},'
        '{"text":"tend","type":"root","meaning_ja":"伸ばす","meaning_en":"stretch","origin":"Latin tendere"}],'
        '"combined_meaning_ja":"外へ伸ばす→延長する","etymology_note":"ラテン語 extendere（外へ伸ばす）由来。"}\n'
        "type must be prefix/root/suffix only. meaning_ja must be Japanese kanji/kana. Output JSON only."
    )

    prompt = f'INPUT: {word}\nOUTPUT:'
    msgs = [
        {"role": "system", "content": FEW_SHOT_SYSTEM},
        {"role": "user",   "content": prompt},
    ]

    def _try_parse(raw: str):
        """rawからJSONを抽出してパース。失敗したらNone。"""
        raw = re.sub(r'```(?:json)?|```', '', raw).strip()
        brace_start = raw.find('{')
        if brace_start == -1: return None
        depth = 0; brace_end = -1
        for idx, ch in enumerate(raw[brace_start:], brace_start):
            if ch == '{': depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0: brace_end = idx; break
        if brace_end == -1: return None
        try: return json.loads(raw[brace_start:brace_end + 1])
        except json.JSONDecodeError: return None

    def _validate_data(d: dict) -> bool:
        """パース済みJSONの品質チェック。Chinese混入・空meaning_jaを弾く。"""
        if not d: return False
        for mo in d.get("morphemes", []):
            mja = mo.get("meaning_ja", "")
            if not mja: return False
            # 日本語文字（ひらがな・カタカナ・漢字）が1文字以上含まれていること
            if not re.search(r'[\u3040-\u9FFF]', mja):
                return False  # 中国語ピンイン・英語のみ = 不正
        return True

    # 1bをデフォルトとして全単語に使用。FEW_SHOTでChinese禁止済みのため品質は十分。
    # 4bへのフォールバックは_validate_data失敗時のみ（35秒問題の修正）。
    global POWER_MODE
    _saved_power = POWER_MODE
    POWER_MODE = "high"
    try:
        data = None
        raw1 = ""
        with SystemSpinner(f"語源解析: {word}", stage="pass1"):
            raw1 = stream_response(msgs, False, len(prompt), temp_override=0.0,
                                   silent=True, max_tokens=250, model="gemma3:1b")
        parsed = _try_parse(raw1 or "")
        data = parsed if (parsed and _validate_data(parsed)) else None

        if data is None:
            print(f"{C['dim']}[/ety] 再解析中...{C['w']}", flush=True)
            with SystemSpinner(f"語源解析: {word} [精密]", stage="pass2"):
                raw2 = stream_response(msgs, False, len(prompt), temp_override=0.0,
                                       silent=True, max_tokens=320, model=MODEL_NAME)
            parsed2 = _try_parse(raw2 or "")
            data = parsed2 if (parsed2 and _validate_data(parsed2)) else parsed2
    finally:
        POWER_MODE = _saved_power

    if data is None:
        return f"{C['r']}[/ety] JSONパース失敗\n{(raw1 or '')[:200]}{C['w']}"

    morphemes = data.get("morphemes", [])
    if not morphemes:
        return f"{C['r']}[/ety] 形態素データなし: {word}{C['w']}"

    # ── 辞書補正: AIの誤意味をポスト補正 ──
    corrected = False
    _uncertain_morphs: list[str] = []
    for mo in morphemes:
        key = mo.get("text", "").lower()
        if key in _MDICT:
            entry = _MDICT[key]
            if entry is not None:
                t_type, t_mja, t_men, t_orig = entry
                if mo.get("type") != t_type or mo.get("meaning_en","").lower() != t_men.lower():
                    mo["type"] = t_type
                    mo["meaning_ja"] = t_mja
                    mo["meaning_en"] = t_men
                    mo["origin"] = t_orig
                    corrected = True
        else:
            # ★[修正/ety-1] 辞書未登録の形態素 = AI が自由に生成した部分
            # meaning_ja が空・1文字・または英語のみの場合はハルシネーション疑い
            mja = mo.get("meaning_ja", "").strip()
            men = mo.get("meaning_en", "").strip()
            if not mja or len(mja) < 2 or (mja and not re.search(r'[\u3040-\u9FFF]', mja)):
                _uncertain_morphs.append(key)
                mo["meaning_ja"] = f"({men})" if men else "（未確認）"
                mo["_uncertain"] = True
            # meaning_en も空なら完全に不明扱い
            if not men:
                mo["_uncertain"] = True
                _uncertain_morphs.append(key)
    if corrected:
        print(f"{C['dim']}[/ety] 辞書補正適用{C['w']}", flush=True)
    if _uncertain_morphs:
        print(f"{C['dim']}[/ety] 未辞書形態素（AI推定）: {', '.join(set(_uncertain_morphs))}{C['w']}", flush=True)

    lines: list[str] = []

    # ── ヘッダー ──
    lines.append(f"\n{C['bold']}{C['c']}━━ Etymology 図鑑 ━━━━━━━━━━━━━━━━━━━━━━{C['w']}")

    # ── 色分け単語表示 ──
    word_colored = ""
    for mo in morphemes:
        t = mo.get("type", "root")
        col = TYPE_COLOR.get(t, C['w'])
        word_colored += f"{col}{C['bold']}{mo.get('text','?')}{C['w']}"
    pos_tag = data.get("pos", "")
    lines.append(f"  {word_colored}  {C['dim']}[{pos_tag}]{C['w']}")

    # ── 凡例 ──
    lines.append(
        f"  {C['b']}■ 接頭辞{C['w']}  "
        f"{C['y']}■ 語根{C['w']}  "
        f"{C['g']}■ 接尾辞{C['w']}"
    )
    lines.append(f"  {'─' * 48}")

    # ── 各形態素 ──
    for mo in morphemes:
        t    = mo.get("type", "root")
        col  = TYPE_COLOR.get(t, C['w'])
        lbl  = TYPE_LABEL.get(t, "  ?   ")
        text = mo.get("text", "?")
        mja  = mo.get("meaning_ja", "")
        men  = mo.get("meaning_en", "")
        orig = mo.get("origin", "")
        # ★[修正/ety-2] 未確認形態素には ⚠ マークを付けてハルシネーションを可視化
        uncertain_mark = f" {C['y']}⚠AI推定{C['w']}" if mo.get("_uncertain") else ""
        lines.append(
            f"  {C['dim']}[{lbl}]{C['w']} "
            f"{col}{C['bold']}{text:<12}{C['w']}"
            f"→ {mja}  {C['dim']}({men}){C['w']}{uncertain_mark}"
        )
        if orig:
            lines.append(f"              {C['dim']}語源: {orig}{C['w']}")

    lines.append(f"  {'─' * 48}")

    # ── 全体の意味 ──
    meaning = data.get("combined_meaning_ja", "")
    if meaning:
        lines.append(f"  {C['c']}意味:{C['w']} {meaning}")

    # ── 語源ノート ──
    note = data.get("etymology_note", "")
    if note:
        lines.append(f"  {C['dim']}{note}{C['w']}")

    lines.append("")
    return "\n".join(lines)


def _cleanup():
    OPTIMIZER.stop(); persist_learning(); PurgeEvidence()

# ===== NEW FEATURES v128.1 =====
def handle_image(prompt: str) -> str:
    if not prompt: return f"{C['r']}usage: /img <prompt>  例: /img 渦巻く銀河{C['w']}"
    try: from PIL import Image, ImageDraw
    except ImportError: return f"{C['y']}Pillowが必要: pip install Pillow{C['w']}"
    with SystemSpinner(f"画像生成: {prompt[:30]}...", stage="img") as sp:
        width, height = 640, 480
        img = Image.new("RGB", (width, height), (10, 10, 30))
        draw = ImageDraw.Draw(img)
        seed = abs(hash(prompt)) % (2**31)
        import random; rng = random.Random(seed)
        prompt_l = prompt.lower()
        cx, cy = width // 2, height // 2
        if any(w in prompt_l for w in ["銀河", "galaxy", "宇宙", "星雲"]):
            for _ in range(3000):
                angle = rng.uniform(0, 2 * math.pi)
                radius = rng.uniform(0, 250)
                sr = radius; sa = angle + sr * 0.02
                x = int(cx + sr * math.cos(sa))
                y = int(cy + sr * math.sin(sa))
                if 0 <= x < width and 0 <= y < height:
                    dist = math.sqrt((x-cx)**2 + (y-cy)**2) / 250.0
                    r_val = int(100 + 155 * (1-dist) * abs(math.sin(sa + seed)))
                    g_val = int(50 + 100 * (1-dist) * abs(math.cos(sa * 0.5 + seed)))
                    b_val = int(150 + 105 * (1-dist))
                    img.putpixel((x, y), (r_val % 256, g_val % 256, b_val % 256))
        elif any(w in prompt_l for w in ["波", "wave", "海", "ocean"]):
            for x in range(width):
                for y_mult in range(3):
                    base_y = height // 2 + int(80 * math.sin(x * 0.03 + y_mult * 2.0 + seed * 0.01))
                    for dy in range(-15, 15):
                        yy = base_y + dy + y_mult * 60
                        if 0 <= yy < height:
                            intensity = max(0, 255 - abs(dy) * 12)
                            img.putpixel((x, yy), (int(intensity*0.3*(1+math.sin(x*0.02+seed))), int(intensity*0.6*(1+math.cos(x*0.025+seed*0.5))), int(intensity*0.9)))
        elif any(w in prompt_l for w in ["炎", "火", "fire", "flame", "夕日"]):
            for x in range(width):
                fh = int(height * 0.6 * (0.5 + 0.5 * math.sin(x * 0.02 + seed * 0.1)))
                for y in range(height - fh, height):
                    ratio = (height - y) / fh
                    var = rng.randint(-20, 20)
                    img.putpixel((x, y), (max(0,min(255,255+var)), max(0,min(255,int(100+155*(1-ratio))+var)), max(0,min(255,int(50*(1-ratio))))))
        elif any(w in prompt_l for w in ["花", "flower", "桜"]):
            for petal in range(8):
                ao = petal * 2 * math.pi / 8 + seed * 0.01
                for r in range(1, 110, 2):
                    for a_step in range(24):
                        a = ao + a_step * 2 * math.pi / 24
                        x = int(cx + r * math.cos(a) * (1 + 0.3 * math.sin(3 * a)))
                        y = int(cy + r * math.sin(a) * (1 + 0.3 * math.sin(3 * a)))
                        if 0 <= x < width and 0 <= y < height:
                            c_val = int(180 + 75 * (1 - r/110))
                            img.putpixel((x, y), (c_val, int(c_val*0.3), int(c_val*0.6)))
        else:
            for i in range(800):
                x = cx + int(math.sin(i * 0.1) * (i * 0.3))
                y = cy + int(math.cos(i * 0.07) * (i * 0.3))
                rv = int(128 + 127 * math.sin(i * 0.05 + seed))
                gv = int(64 + 63 * math.cos(i * 0.03 + seed * 0.5))
                bv = int(200 + 55 * math.sin(i * 0.07 + seed * 0.3))
                draw.ellipse([x-3, y-3, x+3, y+3], fill=(rv % 256, gv % 256, bv % 256))
    filename = f"aegis_img_{int(time.time())}.png"
    img.save(filename)
    return f"{C['g']}画像保存: {filename} ({width}x{height}){C['w']}"

def handle_convert(arg: str) -> str:
    parts = arg.split(None, 2)
    if len(parts) < 3: return f"{C['r']}usage: /convert <from> <to> <text/str>{C['w']}"
    fmt_from, fmt_to, text = parts[0].lower(), parts[1].lower(), parts[2]
    if fmt_from == "md" and fmt_to == "html":
        import html as h
        lines = []
        for line in text.splitlines():
            if line.startswith("# "): lines.append(f"<h1>{h.escape(line[2:])}</h1>")
            elif line.startswith("## "): lines.append(f"<h2>{h.escape(line[3:])}</h2>")
            elif line.startswith("### "): lines.append(f"<h3>{h.escape(line[4:])}</h3>")
            elif line.startswith("- "): lines.append(f"<li>{h.escape(line[2:])}</li>")
            else: lines.append(f"<p>{h.escape(line)}</p>")
        result = "<!DOCTYPE html><html><body>" + "\n".join(lines) + "</body></html>"
    elif fmt_from == "csv" and fmt_to == "json":
        rows = [row.split(",") for row in text.splitlines() if row.strip()]
        if rows: result = json.dumps([dict(zip(rows[0], r)) for r in rows[1:]], ensure_ascii=False, indent=2)
        else: result = "[]"
    elif fmt_from == "tsv" and fmt_to == "json":
        rows = [row.split("\t") for row in text.splitlines() if row.strip()]
        if rows: result = json.dumps([dict(zip(rows[0], r)) for r in rows[1:]], ensure_ascii=False, indent=2)
        else: result = "[]"
    elif fmt_from == "json" and fmt_to == "csv":
        try:
            data = json.loads(text)
            if isinstance(data, list) and data:
                headers = list(data[0].keys())
                csv_lines = [",".join(headers)]
                for item in data:
                    csv_lines.append(",".join(str(item.get(h, "")) for h in headers))
                result = "\n".join(csv_lines)
            else: result = str(data)
        except: return f"{C['r']}JSONパースエラー{C['w']}"
    elif fmt_from == "text" and fmt_to == "html":
        result = f"<!DOCTYPE html><html><body><pre>{html_module.escape(text)}</pre></body></html>"
    else: return f"{C['r']}未対応の変換: {fmt_from}→{fmt_to}{C['w']}"
    fn = f"aegis_convert_{int(time.time())}.{fmt_to}"
    try:
        with open(fn, "w", encoding="utf-8") as f: f.write(result)
        return f"{C['g']}変換完了: {fn} ({len(result)}字){C['w']}"
    except Exception as e: return f"{C['r']}error: {e}{C['w']}"

def handle_qr(text: str) -> str:
    if not text: return f"{C['r']}usage: /qr <text>{C['w']}"
    try:
        import qrcode
        from PIL import Image
    except ImportError: return f"{C['y']}qrcode+pip install qrcode Pillow{C['w']}"
    qr = qrcode.QRCode(box_size=10, border=2)
    qr.add_data(text)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    fn = f"aegis_qr_{int(time.time())}.png"
    img.save(fn)
    return f"{C['g']}QRコード保存: {fn}{C['w']}"

def handle_color(hex_code: str) -> str:
    if not hex_code: return f"{C['r']}usage: /color <hex>  例: /color ff5733{C['w']}"
    hex_code = hex_code.lstrip("#")
    if len(hex_code) != 6:
        try: hex_code = hex(int(hex_code, 16))[2:].zfill(6)
        except: return f"{C['r']}無効な値: {hex_code}{C['w']}"
    if not all(c in "0123456789abcdefABCDEF" for c in hex_code): return f"{C['r']}無効な16進数{C['w']}"
    r, g, b = int(hex_code[0:2], 16), int(hex_code[2:4], 16), int(hex_code[4:6], 16)
    block = f"\033[48;2;{r};{g};{b}m     \033[0m"
    rows = [f"{C['c']}=== 色情報 #{hex_code.upper()} ==={C['w']}"]
    rows.append(f"  RGB: ({r}, {g}, {b})")
    rows.append(f"  サンプル: {block}")
    hsl_h = math.degrees(math.atan2(math.sqrt(3)*(g-b), 2*r-g-b)) % 360
    rows.append(f"  HSL: ({hsl_h:.0f}°, {max(r,g,b)-min(r,g,b)}%, {max(r,g,b)/2.55:.0f}%)")
    return "\n".join(rows)

def handle_sysinfo() -> str:
    import psutil
    boot = time.time() - psutil.boot_time()
    cpu_percent = psutil.cpu_percent(interval=0.5)
    mem = psutil.virtual_memory()
    rows = [f"{C['c']}=== システム情報 ==={C['w']}"]
    rows.append(f"  OS: {platform.system()} {platform.release()}")
    rows.append(f"  Python: {sys.version.split()[0]}")
    rows.append(f"  起動経過: {boot//86400:.0f}d {(boot%86400)//3600:.0f}h {(boot%3600)//60:.0f}m")
    rows.append(f"  CPU使用率: {cpu_percent:.1f}%")
    rows.append(f"  メモリ: {mem.used//(1024**3)}GB / {mem.total//(1024**3)}GB ({mem.percent:.0f}%)")
    return "\n".join(rows)

def handle_rename(arg: str) -> str:
    parts = arg.split(None, 1)
    if len(parts) < 2: return f"{C['r']}usage: /rename <old> <new>{C['w']}"
    old, new = parts[0], parts[1]
    try:
        safe_old = _assert_safe_path(old)
        safe_new = _assert_safe_path(new)
    except ValueError as e:
        return f"{C['r']}セキュリティエラー: {e}{C['w']}"
    if not os.path.exists(safe_old): return f"{C['r']}ファイルなし: {old}{C['w']}"
    # 新しいパスのディレクトリが存在するか確認
    new_dir = os.path.dirname(safe_new)
    if new_dir and not os.path.isdir(new_dir):
        return f"{C['r']}移動先ディレクトリが存在しません: {new_dir}{C['w']}"
    try:
        os.rename(safe_old, safe_new)
        return f"{C['g']}リネーム: {os.path.basename(safe_old)} → {os.path.basename(safe_new)}{C['w']}"
    except Exception as e:
        return f"{C['r']}error: {e}{C['w']}"

def handle_batch(arg: str) -> str:
    parts = arg.split(None, 1)
    if len(parts) < 2: return f"{C['r']}usage: /batch <cmd> <path>  例: /batch count .{C['w']}"
    cmd, path = parts[0].lower(), parts[1].strip()
    try:
        safe_path = _assert_safe_path(path)
    except ValueError as e:
        return f"{C['r']}セキュリティエラー: {e}{C['w']}"
    if not os.path.exists(safe_path): return f"{C['r']}パスなし: {path}{C['w']}"
    if cmd == "count":
        if os.path.isfile(safe_path):
            with open(safe_path, "r", encoding="utf-8", errors="ignore") as f: data = f.read()
            return f"{C['g']}行数: {data.count(chr(10))+1}, 文字数: {len(data)}{C['w']}"
        else:
            files = [f for f in os.listdir(safe_path) if os.path.isfile(os.path.join(safe_path, f))]
            return f"{C['g']}ファイル数: {len(files)}{C['w']}"
    elif cmd == "size":
        if os.path.isfile(safe_path): return f"{C['g']}サイズ: {os.path.getsize(safe_path)} bytes{C['w']}"
        total = sum(os.path.getsize(os.path.join(safe_path, f)) for f in os.listdir(safe_path) if os.path.isfile(os.path.join(safe_path, f)))
        return f"{C['g']}合計サイズ: {total//1024}KB{C['w']}"
    elif cmd == "list":
        if os.path.isdir(safe_path):
            items = os.listdir(safe_path)
            return f"{C['c']}=== {path} ({len(items)}件) ==={C['w']}\n" + "\n".join(items[-50:])
        return f"{C['r']}ディレクトリではありません{C['w']}"
    return f"{C['r']}未対応コマンド: {cmd}{C['w']}"

def handle_chart(data_str: str) -> str:
    if not data_str: return f"{C['r']}usage: /chart <data>  例: /chart bar: cats=30,dogs=45,birds=15{C['w']}"
    try:
        parts = data_str.split(None, 1)
        chart_type = parts[0].lower().rstrip(":") if parts else "bar"
        data_part = parts[1] if len(parts) > 1 else data_str
        if ":" in data_part and not data_part.startswith(chart_type):
            chart_type = data_part.split(":")[0].strip().lower()
            data_part = ":".join(data_part.split(":")[1:])
        items = [item.strip() for item in data_part.replace("，",",").replace("、",",").split(",") if item.strip()]
        pairs = []
        for item in items:
            if "=" in item:
                k, v = item.split("=", 1)
                pairs.append((k.strip(), float(v.strip())))
            elif ":" in item:
                k, v = item.split(":", 1)
                pairs.append((k.strip(), float(v.strip())))
        if not pairs: return f"{C['r']}データ形式が不明: name=value,name=value{C['w']}"
        max_val = max(v for _, v in pairs)
        scale = 30 / max(max_val, 1)
        lines = [f"{C['c']}=== チャート ({chart_type}) ==={C['w']}"]
        if chart_type.startswith("bar"):
            for name, val in pairs:
                bar = "█" * max(1, int(val * scale))
                lines.append(f"  {name:12s} {bar} {val:.0f}")
        elif chart_type.startswith("pie"):
            total = sum(v for _, v in pairs)
            for name, val in pairs:
                pct = val / total * 100
                bar = "▓" * max(1, int(pct / 3))
                lines.append(f"  {name:12s} {bar} {pct:.1f}%")
        else:
            points = []
            for i, (name, val) in enumerate(pairs):
                x = int(i * 60 / max(len(pairs)-1, 1))
                y = int(20 - val * scale / 2)
                points.append((x, y))
                lines.append(f"  {name:10s} {'▬'*max(1,int(val*scale))} {val:.0f}")
        return "\n".join(lines)
    except Exception as e: return f"{C['r']}chart error: {e}{C['w']}"

def handle_note(text: str) -> str:
    if not text: return f"{C['r']}usage: /note <text>{C['w']}"
    fn = f"aegis_notes_{time.strftime('%Y%m%d')}.txt"
    with open(fn, "a", encoding="utf-8") as f: f.write(f"[{now_stamp()}] {text}\n")
    return f"{C['g']}ノート保存: {fn}{C['w']}"

def handle_timer(seconds_str: str) -> str:
    try: seconds = int(seconds_str)
    except: return f"{C['r']}usage: /timer <seconds>{C['w']}"
    if seconds < 1 or seconds > 86400: return f"{C['r']}1-86400秒の範囲で{C['w']}"
    def _timer():
        import time as t
        t.sleep(seconds)
        print(f"\n{C['g']}⏰ タイマー終了 ({seconds}秒経過){C['w']}")
    threading.Thread(target=_timer, daemon=True).start()
    return f"{C['g']}タイマー設定: {seconds}秒後にお知らせ{C['w']}"

def handle_calc(expr: str) -> str:
    if not expr: return f"{C['r']}usage: /calc <expression>{C['w']}"
    import ast as _ast
    _ALLOWED_NODES = {
        _ast.Expression, _ast.BinOp, _ast.UnaryOp, _ast.Call,
        _ast.Attribute, _ast.Name, _ast.Constant, _ast.Load,
        _ast.Add, _ast.Sub, _ast.Mult, _ast.Div, _ast.Mod,
        _ast.Pow, _ast.FloorDiv, _ast.USub, _ast.UAdd,
    }
    expr = expr.replace("^", "**").replace("×", "*").replace("÷", "/")
    try:
        tree = _ast.parse(expr, mode="eval")
    except SyntaxError as e:
        return f"{C['r']}構文エラー: {e}{C['w']}"
    for node in _ast.walk(tree):
        if type(node) not in _ALLOWED_NODES:
            return f"{C['r']}許可されていない操作: {type(node).__name__}{C['w']}"
        if isinstance(node, _ast.Attribute) and node.attr.startswith("_"):
            return f"{C['r']}プライベート属性へのアクセスは禁止{C['w']}"
        if isinstance(node, _ast.Name) and node.id.startswith("_"):
            return f"{C['r']}プライベート名は使用不可{C['w']}"
    try:
        ns = {"__builtins__": {}, "math": math}
        result = eval(compile(tree, "<calc>", "eval"), ns)
        return f"{C['g']}= {result}{C['w']}"
    except Exception as e:
        return f"{C['r']}error: {e}{C['w']}"

# ===== 追加ハンドラ =====
SESSION_STATS = {"start_time": 0.0, "response_times": [], "token_estimates": []}

def handle_export(arg: str, ms: list) -> str:
    fmt = arg.strip().lower() or "md"
    if fmt not in ("md", "markdown", "json", "txt"): return f"{C['r']}形式: md / json / txt{C['w']}"
    ts = time.strftime("%Y%m%d_%H%M%S")
    fn = f"aegis_export_{ts}.{fmt}"
    try:
        if fmt in ("md", "markdown"):
            lines = [f"# Aegis 会話ログ ({now_stamp()})\n"]
            for m in ms:
                prefix = f"## {USER_NAME}" if m["role"] == "user" else "## AI"
                lines.append(f"\n{prefix}\n\n{m.get('content', '')}\n")
            with open(fn, "w", encoding="utf-8") as f: f.writelines(lines)
        elif fmt == "json":
            with open(fn, "w", encoding="utf-8") as f: json.dump(ms, f, ensure_ascii=False, indent=2)
        else:
            with open(fn, "w", encoding="utf-8") as f:
                for m in ms: f.write(f"{m['role']}: {m.get('content', '')}\n\n")
        return f"{C['g']}出力: {fn} ({len(ms)}メッセージ){C['w']}"
    except Exception as e: return f"{C['r']}export error: {e}{C['w']}"

def handle_stats() -> str:
    elapsed = time.time() - SESSION_STATS["start_time"]
    rt = SESSION_STATS.get("response_times", [])
    avg_rt = sum(rt) / max(len(rt), 1)
    return "\n".join(r for r in [
        f"{C['c']}=== セッション統計 ==={C['w']}",
        f"経過: {elapsed//3600:.0f}h {(elapsed%3600)//60:.0f}m",
        f"対話数: {LEARNING_STATS['total_interactions']}",
        f"肯定/否定/修正: {LEARNING_STATS['positive_count']}/{LEARNING_STATS['negative_count']}/{LEARNING_STATS['self_correction_count']}",
        f"平均応答: {avg_rt:.1f}s" if rt else "",
        f"RAG: {len(RAG_CACHE)} | ベクトル: {vector_count()}",
        f"温度: {TEMP_VOICE:.2f} | 最適化: {len(PROMPT_OPTIMIZATIONS)}カテゴリ",
    ] if r)

def handle_template(arg: str) -> str:
    state = load_state(); templates = state.setdefault("templates", {})
    sub, _, rest = arg.partition(" "); sub = sub.strip().lower(); rest = rest.strip()
    if not arg or sub == "list":
        if not templates: return f"{C['y']}テンプレートなし{C['w']}"
        return f"{C['c']}=== テンプレート一覧 ==={C['w']}\n" + "\n".join(f"  {k}: {v[:60]}..." for k, v in templates.items())
    if sub == "add":
        if "|" not in rest: return f"{C['r']}usage: /template add <名前> | <内容>{C['w']}"
        name, _, content = rest.partition("|"); name = name.strip(); content = content.strip()
        if not name or not content: return f"{C['r']}usage: /template add <名前> | <内容>{C['w']}"
        templates[name] = content; save_state(state)
        return f"{C['g']}テンプレート保存: {name} ({len(content)}字){C['w']}"
    if sub == "del":
        if not rest or rest not in templates: return f"{C['r']}usage: /template del <名前>{C['w']}"
        del templates[rest]; save_state(state)
        return f"{C['y']}削除: {rest}{C['w']}"
    if sub in templates: return f"{C['c']}=== {sub} ==={C['w']}\n{templates[sub]}"
    return f"{C['r']}usage: /template add/list/del{C['w']}"

def handle_history(arg: str) -> str:
    if not arg:
        if not INTERACTION_LOG: return f"{C['y']}履歴なし{C['w']}"
        lines = [f"{C['c']}=== 直近の対話 ==={C['w']}"]
        for i, entry in enumerate(INTERACTION_LOG[-20:], 1):
            t = time.strftime("%H:%M", time.localtime(entry.get("time", 0)))
            fb = entry.get("feedback", 0)
            lines.append(f"  {i}. [{t}] {'+' if fb>0 else '-' if fb<0 else ' '} {entry.get('input','')[:50]}")
        return "\n".join(lines)
    keyword = arg.lower()
    hits = [e for e in INTERACTION_LOG if keyword in e.get("input", "").lower()]
    if not hits: return f"{C['y']}「{arg}」に一致する履歴なし{C['w']}"
    lines = [f"{C['c']}=== 履歴検索: {arg} ({len(hits)}件) ==={C['w']}"]
    for e in hits[-10:]:
        t = time.strftime("%m/%d %H:%M", time.localtime(e.get("time", 0)))
        lines.append(f"  [{t}] {'+' if e.get('feedback',0)>0 else '-' if e.get('feedback',0)<0 else ' '} {e.get('input','')[:80]}")
    return "\n".join(lines)

def handle_tts(text: str) -> str:
    try:
        import edge_tts, asyncio
    except ImportError: return f"{C['y']}edge-tts 未インストール: pip install edge-tts{C['w']}"
    if not text: return f"{C['r']}usage: /tts <テキスト>{C['w']}"
    try:
        fn = f"tts_{int(time.time())}.mp3"
        asyncio.run(edge_tts.Communicate(text, voice="ja-JP-NanamiNeural").save(fn))
        mpv = shutil.which("mpv")
        if mpv: S.Popen([mpv, "--no-video", fn], stdout=S.DEVNULL, stderr=S.DEVNULL); return f"{C['g']}音声再生: {fn}{C['w']}"
        return f"{C['g']}音声保存: {fn}{C['w']}"
    except Exception as e: return f"{C['r']}TTS error: {e}{C['w']}"

def handle_translate(text: str, target_lang: str = "en") -> str:
    if not text: return f"{C['r']}usage: /tr <言語> <テキスト>{C['w']}"
    sys_prompt = f"あなたは翻訳者。以下のテキストを{target_lang}に翻訳せよ。翻訳以外の出力は一切禁止。"
    print(f"{C['c']}[翻訳 {target_lang}]{C['w']}: ", end="", flush=True)
    result = stream_response([{"role": "system", "content": sys_prompt}, {"role": "user", "content": text}], True, len(text), 0.15, silent=False)
    return result or f"{C['r']}翻訳失敗{C['w']}"

def handle_elab(text: str, per_id: int) -> str:
    if not text: return f"{C['r']}usage: /elab <説明してほしい内容>{C['w']}"
    persona = get_persona(per_id)
    print(f"{C['c']}{persona['name']} [深層推論]{C['w']}: ", end="", flush=True)
    return stream_response([get_sys_prm("elab", text, per_id=per_id), {"role": "user", "content": f"以下の内容を、比喩・例えを用いて分かりやすく説明してください:\n{text}"}], True, len(text), 0.62, model=DEEP_MODEL) or ""

def handle_comp(args: str) -> str:
    # ★[修正/comp-1] "s <数字>" 記法を単一IDトークンに正規化してから分割
    # 例: "s 19 s 13 世界" → ["19", "13", "世界"]
    _raw = args.replace("\u3000", " ").strip()
    _raw = re.sub(r'\bs\s+(\d+)\b', r'\1', _raw)   # "s 19" → "19"
    parts = re.split(r'\s+', _raw)
    if len(parts) < 2: return f"{C['r']}usage: /comp <ID or 名前> <ID or 名前> [テーマ]{C['w']}"
    id1, id2 = parts[0], parts[1]
    theme = " ".join(parts[2:]) if len(parts) >= 3 else "自由会話"
    p1 = get_persona(int(id1)) if id1.isdigit() and 1 <= int(id1) <= 24 else {"name": id1, "style": f"{id1}の口調で話す", "first_person": "私"}
    p2 = get_persona(int(id2)) if id2.isdigit() and 1 <= int(id2) <= 24 else {"name": id2, "style": f"{id2}の口調で話す", "first_person": "私"}

    # ★[修正/comp-2] モード判定: 哲学者(1-36)同士 → 哲学的対話モードを新設
    PHILOSOPHER_IDS = set(range(1, 25))
    BUSINESS_KW = {"社長", "部長", "課長", "教授", "博士", "先生", "CEO", "CTO", "役員", "責任者", "マネージャ", "マネージャー", "リーダー", "秘書", "S-01", "執事", "医師", "秀才", "エンジニア", "管理職", "弁護士", "会計士", "コンサル", "アナリスト", "ディレクター", "プロデューサー"}
    CASUAL_NAME_KW = {"お嬢様", "おじょうさま", "ギャル", "ツンデレ", "クール", "無口", "元気", "子供", "魔王", "勇者", "魔法使い", "忍者", "侍", "ヤンキー", "天然", "腹黒", "中二病", "猫", "犬", "恋人", "友達", "彼女", "彼氏", "妹", "姉", "弟", "兄", "ママ", "パパ"}
    CASUAL_PERSONA_IDS = set(range(1, 25))  # 哲学者全員をcasual判定から除外し、philosopher優先
    CASUAL_THEME_KW = {"デート", "遊び", "旅行", "趣味", "カフェ", "雑談", "休日", "暇", "好き", "恋愛", "友達", "買い物", "ゲーム", "アニメ", "映画", "音楽", "料理", "ペット", "おしゃべり", "海", "山", "花見", "キャンプ", "飲み", "食事", "遊ぼう", "話そう", "悩み", "日常", "たわいもない"}
    p1_phil = id1.isdigit() and int(id1) in PHILOSOPHER_IDS
    p2_phil = id2.isdigit() and int(id2) in PHILOSOPHER_IDS
    p1_biz = (not p1_phil) and (any(k in p1["name"] for k in BUSINESS_KW))
    p2_biz = (not p2_phil) and (any(k in p2["name"] for k in BUSINESS_KW))
    p1_cas = (not p1_phil) and (any(k in p1["name"] for k in CASUAL_NAME_KW))
    p2_cas = (not p2_phil) and (any(k in p2["name"] for k in CASUAL_NAME_KW))
    if p1_phil and p2_phil:
        is_philosophical = True; is_casual = False
    elif p1_biz or p2_biz:
        # 明示的なビジネスキーワードがある場合のみビジネスモード
        is_philosophical = False; is_casual = False
    elif p1_cas or p2_cas or any(kw in theme for kw in CASUAL_THEME_KW):
        # どちらか一方でもカジュアルキーワードがあればカジュアル
        # 織田信長+ギャル、中立+ギャルなど「片方だけ」にも対応
        is_philosophical = False; is_casual = True
    else:
        # 明示的な分類なし（織田信長+織田信長など）→ カジュアルにデフォルト
        # ビジネスはBUSINESS_KWが明示された場合のみ
        is_philosophical = False; is_casual = True
    mode_label = "哲学的対話" if is_philosophical else ("カジュアル" if is_casual else "ビジネス")
    print(f"{C['y']}=== {mode_label}: {p1['name']} vs {p2['name']} ({theme}) ==={C['w']}")
    fp1, fp2 = p1.get("first_person", "私"), p2.get("first_person", "私")
    labels = ["[テーゼ]", "[反テーゼ/否定]", "[保存]", "[高揚/アウフヘーベン]", "[合意条件]"]

    def _role_axis(name: str) -> str:
        if is_casual:
            casual_map = {
                "伴侶": "恋人として本音で語る。建前より気持ち優先。",
                "AI様": "全能の存在として慈愛と叡智で語る。",
                "後輩": "後輩として素直な疑問と尊敬を交えて語る。",
                "女王": "女王として寛大さと気高さで語る。",
                "ママ": "母親として温かく包容力をもって語る。",
                "お嬢様": "お嬢様として上品で少し世間知らずな視点で。",
                "博士": "博士として好奇心旺盛に語る。",
                "忍者": "忍者として簡潔で観察力鋭く語る。",
                "妹": "妹として甘えん坊で素直に語る。",
                "メイド": "メイドとして献身的で温かく語る。",
                "先生": "先生として教え導く立場から語る。",
                "中二病": "中二病として厨二的で情熱的に語る。",
                "秘書": "秘書として冷静で的確に助言する。",
            }
            for key, desc in casual_map.items():
                if key in name: return desc
            return "対等な関係としてお互いの意見を尊重しながら自然に語る。"
        senior = any(w in name for w in ("ベテラン", "CTO", "部長", "責任者", "社長", "役員", "リード", "シニア"))
        junior = any(w in name for w in ("新卒", "新人", "若手", "ジュニア", "研修", "インターン"))
        legal = any(w in name for w in ("法務", "監査", "コンプライアンス"))
        sales = any(w in name for w in ("営業", "事業", "企画"))
        if senior:
            return "経験者として、責任・設計・運用・失敗時の被害範囲を語る。抽象論でなく判断基準を出す。"
        if junior:
            return "新卒として、現場で詰まる点・レビュー待ち・学習不足・実装手順の不安を率直に質問する。上位者ぶらない。"
        if legal:
            return "法務として、契約・規制・監査証跡・責任分界を語る。"
        if sales:
            return "事業側として、顧客価値・売上・導入スピードを語る。"
        return "その肩書きに固有の利害・制約・語彙で話す。"

    axis1, axis2 = _role_axis(p1['name']), _role_axis(p2['name'])

    # ── KB知識ベース注入 ─────────────────────────────────────────
    kb_context_block = ""
    _kb_cols = [c for c in vector_list_collections() if c != "s01_memory"]
    if _kb_cols:
        _kb_hits: list[str] = []
        for _col in _kb_cols:
            _src = _col.replace("book_", "")
            for _h in vector_search(theme, n=2, collection=_col):
                _kb_hits.append(f"《{_src}》: {_h[:220]}")
        if _kb_hits:
            kb_context_block = (
                "\n【知識ベース参照（この内容を議論の根拠・引用として積極的に使え）】\n"
                + "\n".join(_kb_hits[:6])
            )
            print(f"{C['dim']}[comp: KB {len(_kb_hits)}件参照]{C['w']}")

    theme_terms = [w for w in re.findall(r'[A-Za-z0-9_\-]{3,}|[ァ-ヶー]{3,}|[一-龯]{2,}', theme) if len(w) >= 2]
    common_stop = {p1['name'], p2['name'], "テーゼ", "反テーゼ", "否定", "保存", "高揚", "アウフヘーベン", "合意条件", "について", "する", "です", "ます", "こと", "もの", "ため", "具体", "初期", "条件"}

    def _too_repetitive(raw: str) -> bool:
        words = [w for w in re.findall(r'[A-Za-z0-9_\-]{3,}|[ァ-ヶー]{3,}|[一-龯]{2,}', raw) if w not in common_stop]
        counts = Counter(words)
        if any(counts.get(t, 0) >= 5 for t in theme_terms): return True
        return any(v >= 6 for k, v in counts.items() if k not in theme_terms)

    if is_philosophical:
        # ★[修正/comp-3] 哲学者同士の専用対話モード — ビジネス/カジュアルの枠を排除
        system = (
            "あなたは哲学的対話の記録者。形式的な会議や日常会話ではなく、思想の自然な衝突と展開を書く。\n"
            "出力は必ず5発言。途中で終わるな。前置き・解説・箇条書きは禁止。Markdown装飾禁止。\n"
            "各哲学者は自分固有の哲学的立場・概念・語法で思考し語る。相手の言葉を受けて自分の思想で応答する。\n"
            "弁証法的な流れ（テーゼ→反テーゼ→保存→高揚→応答）を意識しつつ、各哲学者の用語で自然に展開せよ。\n"
            "同じ語句・同じ結論の反復は禁止。各発言は前発言の一点のみを受け、必ず新しい思想的視点を加える。"
        )
        user = (
            f"テーマ: 「{theme}」\n"
            f"話者A: {p1['name']}。哲学的立場と語法（厳守）: {p1['style']}。一人称: {fp1}。\n"
            f"話者B: {p2['name']}。哲学的立場と語法（厳守）: {p2['style']}。一人称: {fp2}。\n"
            f"{kb_context_block}\n"
            f"次の5発言を、各哲学者の立場と語法を完全に守って書け。\n"
            f"{p1['name']} [テーゼ]: 「{theme}」について自分の哲学的立場から最初の問いや主張を立てる。\n"
            f"{p2['name']} [反テーゼ/否定]: 相手の主張を自分の哲学的概念で受け取り、批判または別視点を提示する。\n"
            f"{p1['name']} [保存]: 相手の批判を受け止め、自分の思想で守れる核心を言語化する。\n"
            f"{p1['name']} [高揚/アウフヘーベン]: 二つの立場を統合し、より深い問いや思想へと展開する。\n"
            f"{p2['name']} [合意条件]: この思想展開に対して、自分の哲学的立場から応答または問い返す。"
        )
    elif is_casual:
        system = (
            "あなたは会話ファシリテーター兼脚本家。自然な日常会話の流れだけを書く。\n"
            "出力は必ず5発言。途中で終わるな。前置き・解説・箇条書きは禁止。\n"
            "ヘーゲル式のアウフヘーベンを会話にする。テーゼ、反テーゼによる否定、保存、高揚、合意条件の順に進める。\n"
            "否定=通らない考えを退ける。保存=元の考えの良い部分を残す。高揚=否定と保存を統合し、より良い考えに発展させる。\n"
            "ペルソナを逆転させるな。各キャラは自分の性格・立場に沿った言葉で話す。\n"
            "同じ語句・同じ結論の反復は禁止。各発言は前発言の一点だけを受け、必ず新しい視点を足す。Markdown装飾は禁止。"
        )
        user = (
            f"テーマ: {theme}\n"
            f"話者A: {p1['name']}。口調:{p1['style']}。一人称:{fp1}。この会話での立ち位置:{axis1}\n"
            f"話者B: {p2['name']}。口調:{p2['style']}。一人称:{fp2}。この会話での立ち位置:{axis2}\n"
            f"{kb_context_block}\n"
            "次の5行ラベルを必ず全て使う。各発言は2文以内。日常会話として自然に書く。\n"
            f"{p1['name']} [テーゼ]: 自分の気持ちや考えを最初に出す。\n"
            f"{p2['name']} [反テーゼ/否定]: 自分の立場から、違う意見や気持ちを伝える。\n"
            f"{p1['name']} [保存]: 相手の意見を受け止め、自分の考えの中で残したい部分を明確にする。\n"
            f"{p1['name']} [高揚/アウフヘーベン]: 二人の意見を統合した、より良い考えや落とし所を提案する。\n"
            f"{p2['name']} [合意条件]: その提案に対する自分の条件や次のアクションを伝える。"
        )
    else:
        system = (
            "あなたは会議ファシリテーター兼脚本家。実際の会議の自然な発言だけを書く。\n"
            "出力は必ず5発言。途中で終わるな。前置き・解説・箇条書きは禁止。\n"
            "ヘーゲル式のアウフヘーベンを会話にする。テーゼ、反テーゼによる否定、保存、高揚、合意条件の順に進める。\n"
            "否定=通らない点を退ける。保存=元案の価値ある目的を残す。高揚=否定と保存を統合し、上位の実行案へ組み替える。\n"
            "ペルソナを逆転させるな。経験者は経験者らしく、新卒は新卒らしく、役職固有の制約で話す。\n"
            "同じ語句・同じ結論の反復は禁止。各発言は前発言の一点だけを受け、必ず新しい論点を足す。Markdown装飾は禁止。テーマの主語を別事業に置き換えるな。"
        )
        user = (
            f"テーマ: {theme}\n"
            f"話者A: {p1['name']}。口調:{p1['style']}。一人称:{fp1}。役割固定:{axis1}\n"
            f"話者B: {p2['name']}。口調:{p2['style']}。一人称:{fp2}。役割固定:{axis2}\n"
            f"{kb_context_block}\n"
            "次の5行ラベルを必ず全て使う。各発言は2文以内。会議室での会話として書く。\n"
            f"{p1['name']} [テーゼ]: 自分の職責から、初期案と狙いを具体的に言う。\n"
            f"{p2['name']} [反テーゼ/否定]: 自分の経験値と職責に合う言い方で、通らない点を一つ否定する。\n"
            f"{p1['name']} [保存]: 否定を受け、元案から残すべき価値・目的・条件を明確にする。\n"
            f"{p1['name']} [高揚/アウフヘーベン]: 否定した点と保存した価値を統合し、上位の実行案へ組み替える。\n"
            f"{p2['name']} [合意条件]: 自分の立場から、実行前の条件と次アクションを合意する。"
        )
    _gen_model = DEEP_MODEL if is_philosophical else MODEL_NAME
    _gen_temp  = 0.52 if is_philosophical else 0.38
    raw = stream_response([{"role": "system", "content": system}, {"role": "user", "content": user}], False, len(user), _gen_temp, silent=True, max_tokens=900, model=_gen_model) or ""
    bad = any(label not in raw for label in labels) or _too_repetitive(raw)
    if bad:
        _axis_hint = (
            f"{p1['name']}は自分の哲学的立場で語る。{p2['name']}は自分の哲学的立場で語る。"
            if is_philosophical else
            f"{p1['name']}はこの軸を守る: {axis1}\n{p2['name']}はこの軸を守る: {axis2}"
        )
        repair = (
            "出力を作り直してください。問題: 必須ラベル不足、ペルソナ逆転、または同語反復。\n"
            "必須ラベル: [テーゼ], [反テーゼ/否定], [保存], [高揚/アウフヘーベン], [合意条件]\n"
            f"{_axis_hint}\n"
            "同じ名詞を繰り返さず、各発言で別の具体論点を出す。\n\n"
            f"テーマ: {theme}\n不完全な出力:\n{raw}"
        )
        raw = stream_response([{"role": "system", "content": system}, {"role": "user", "content": repair}], False, len(repair), 0.30, silent=True, max_tokens=950, model=_gen_model) or raw
    if any(label not in raw for label in labels) or _too_repetitive(raw):
        if is_philosophical:
            raw = (
                f"{p1['name']} [テーゼ]: 「{theme}」とは何か。私はこう問わざるをえない。\n"
                f"{p2['name']} [反テーゼ/否定]: その問い自体がすでに誤った前提を含んでいる。私はそこから問い直す必要がある。\n"
                f"{p1['name']} [保存]: しかし問うこと自体の意義は否定されない。私の核心はそこにある。\n"
                f"{p1['name']} [高揚/アウフヘーベン]: 二つの立場を統合すれば、問い方そのものを変えることが求められる。\n"
                f"{p2['name']} [合意条件]: その変容を認めよう。だがそれは新たな問いの始まりに過ぎない。"
            )
        elif is_casual:
            raw = (
                f"{p1['name']} [テーゼ]: ねえ、{theme}について話そうよ！私はこういうアイデアがあるんだけど。\n"
                f"{p2['name']} [反テーゼ/否定]: うーん、それもいいけど、私はちょっと違うかな。もっとこういう風にできない？\n"
                f"{p1['name']} [保存]: なるほど、そういう考えもあるね。でも、私の最初のアイデアのこの部分は残したいな。\n"
                f"{p1['name']} [高揚/アウフヘーベン]: じゃあさ、私のアイデアと君のアイデアを合わせて、こういうのはどう？\n"
                f"{p2['name']} [合意条件]: いいね！それなら賛成。まずはこれから始めてみよう。"
            )
        else:
            raw = (
                f"{p1['name']} [テーゼ]: {theme}について、私は段階的に進める案を推します。役割分担を明確にし、リスクを分散しながら進めることが重要だと思います。\n"
                f"{p2['name']} [反テーゼ/否定]: おっしゃる方向性は理解できますが、段階的すぎると意思決定が遅れます。{theme}では特に初動のスピードが成否を分けると考えます。\n"
                f"{p1['name']} [保存]: スピードの重要性は同意します。ただ、{theme}において責任の所在を曖昧にしたままでは後で問題が大きくなるリスクがあります。\n"
                f"{p1['name']} [高揚/アウフヘーベン]: ならば、{theme}の核心部分は迅速に進め、リスクの高い判断領域だけ段階的に決裁する二層構造にしませんか。\n"
                f"{p2['name']} [合意条件]: その案であれば賛成できます。まず優先度の高い領域から着手し、判断基準を共有しながら進めましょう。"
            )
    raw = raw.replace("**", "")
    print(raw.strip())
    return f"{C['y']}=== 対話終了 ==={C['w']}"

# ===== 自己弁証法: テーゼ/アンチテーゼ分解 =====
def handle_split(args: str) -> str:
    """/split <ID or 名前> [テーマ]
    1つのペルソナをテーゼ的・アンチテーゼ的サブペルソナに分解し、内的弁証法を生成する。
    """
    _raw = re.sub(r'\bs\s+(\d+)\b', r'\1', args.replace("\u3000", " ").strip())
    parts = re.split(r'\s+', _raw)
    if not parts or not parts[0]:
        return f"{C['r']}usage: /split <ID or 名前> [テーマ]{C['w']}"
    id1 = parts[0]
    theme = " ".join(parts[1:]) if len(parts) > 1 else "自己の核心"
    base = (get_persona(int(id1)) if id1.isdigit() and 1 <= int(id1) <= 24
            else {"name": id1, "style": f"{id1}らしい思想と口調", "first_person": "私"})

    print(f"{C['y']}=== 自己分解: {base['name']} → テーゼ / アンチテーゼ ({theme}) ==={C['w']}")
    print(f"{C['dim']}[split: サブペルソナ生成中...]{C['w']}", flush=True)

    # ── Step1: LLMでテーゼ/アンチテーゼを生成（JSON） ──────────────────
    decomp_sys = (
        "あなたは哲学的ペルソナ分析者。与えられた哲学者・人物を"
        "テーゼ的側面（肯定・核心的信念・理想）と"
        "アンチテーゼ的側面（懐疑・矛盾・自己批判・影の部分）の2サブペルソナに分解する。\n"
        "出力はJSON形式のみ。前置き・説明・コードブロック記号は一切不要:\n"
        '{"thesis":{"name":"...","style":"...","fp":"..."},'
        '"antithesis":{"name":"...","style":"...","fp":"..."}}'
    )
    decomp_user = (
        f"人物: {base['name']}\n"
        f"スタイル: {base['style'][:200]}\n"
        f"テーマ: {theme}\n\n"
        f"name は「{base['name']}（テーゼ）」「{base['name']}（アンチテーゼ）」形式。"
        f"style は各側面の口調・立場・語法を60字以内で。fp は一人称（私/僕/俺 など）。"
    )
    raw_json = stream_response(
        [{"role": "system", "content": decomp_sys}, {"role": "user", "content": decomp_user}],
        True, len(decomp_user), temp_override=0.30, silent=True, model=DEEP_MODEL
    ) or ""

    p_thesis = p_anti = None
    try:
        m = re.search(r'\{[\s\S]*\}', raw_json)
        if m:
            data = json.loads(m.group())
            t, a = data.get("thesis", {}), data.get("antithesis", {})
            p_thesis = {"name": t.get("name", f"{base['name']}（テーゼ）"),
                        "style": t.get("style", base["style"]),
                        "first_person": t.get("fp", base.get("first_person", "私"))}
            p_anti   = {"name": a.get("name", f"{base['name']}（アンチテーゼ）"),
                        "style": a.get("style", base["style"]),
                        "first_person": a.get("fp", base.get("first_person", "私"))}
    except Exception as _e:
        print(f"{C['y']}[WARN] ペルソナ解析失敗: {_e}{C['w']}")

    # フォールバック
    if not p_thesis:
        p_thesis = {"name": f"{base['name']}（テーゼ）",
                    "style": base["style"] + " 核心的信念を確信をもって肯定する。",
                    "first_person": base.get("first_person", "私")}
    if not p_anti:
        p_anti   = {"name": f"{base['name']}（アンチテーゼ）",
                    "style": base["style"] + " 自らの思想の矛盾・限界・影の部分を鋭く批判する。",
                    "first_person": base.get("first_person", "私")}

    print(f"{C['c']}テーゼ      : {p_thesis['name']}{C['w']}")
    print(f"            {C['dim']}{p_thesis['style'][:70]}{C['w']}")
    print(f"{C['p']}アンチテーゼ: {p_anti['name']}{C['w']}")
    print(f"            {C['dim']}{p_anti['style'][:70]}{C['w']}")
    print()

    # ── Step2: 分解済みサブペルソナで内的弁証法を生成 ────────────────
    labels = ["[テーゼ]", "[反テーゼ/否定]", "[保存]", "[高揚/アウフヘーベン]", "[合意条件]"]
    fp1, fp2 = p_thesis["first_person"], p_anti["first_person"]

    system = (
        "あなたは自己弁証法の記録者。同一人物の内部で起きる思想的対話を書く。\n"
        "テーゼ側は核心的信念を語り、アンチテーゼ側はその矛盾・限界を内側から突く。\n"
        "出力は必ず5発言。前置き・解説・箇条書き・Markdown装飾は禁止。\n"
        "各発言は2〜3文。同じ語句の反復禁止。各発言は前発言の一点のみを受け新たな視点を加える。"
    )
    user = (
        f"テーマ: 「{theme}」\n"
        f"話者A（テーゼ）: {p_thesis['name']}。立場: {p_thesis['style']}。一人称: {fp1}。\n"
        f"話者B（アンチテーゼ）: {p_anti['name']}。立場: {p_anti['style']}。一人称: {fp2}。\n\n"
        f"次の5発言を、各立場の語法を完全に守って書け:\n"
        f"{p_thesis['name']} [テーゼ]: 「{theme}」について核心的信念から主張する。\n"
        f"{p_anti['name']} [反テーゼ/否定]: その主張の矛盾・盲点・限界を内側から批判する。\n"
        f"{p_thesis['name']} [保存]: 批判を受け止め、それでも守れる思想の核心を言語化する。\n"
        f"{p_thesis['name']} [高揚/アウフヘーベン]: テーゼとアンチテーゼを統合し、より深い地点へ展開する。\n"
        f"{p_anti['name']} [合意条件]: その展開に対し、さらなる問いや留保を提示する。"
    )
    raw = stream_response(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        False, len(user), 0.55, silent=True, max_tokens=900, model=DEEP_MODEL
    ) or ""

    if any(label not in raw for label in labels):
        repair = (
            "必須ラベルが不足しています。以下のラベルを全て使って書き直してください:\n"
            "[テーゼ], [反テーゼ/否定], [保存], [高揚/アウフヘーベン], [合意条件]\n"
            f"テーマ: {theme}\n不完全な出力:\n{raw}"
        )
        raw = stream_response(
            [{"role": "system", "content": system}, {"role": "user", "content": repair}],
            False, len(repair), 0.30, silent=True, max_tokens=950, model=DEEP_MODEL
        ) or raw

    raw = raw.replace("**", "")
    print(raw.strip())
    return f"{C['y']}=== 自己弁証法終了 ==={C['w']}"

# ===== チェスエンジン v1.0 =====
class ChessEngine:
    """本格的なチェスエンジン。完全な駒移動バリデーション・チェック/チェックメイト検出・特殊手対応。"""

    UNICODE_PIECES = {
        "wK": "♔", "wQ": "♕", "wR": "♖", "wB": "♗", "wN": "♘", "wP": "♙",
        "bK": "♚", "bQ": "♛", "bR": "♜", "bB": "♝", "bN": "♞", "bP": "♟",
    }
    ASCII_PIECES = {
        "wK": "K", "wQ": "Q", "wR": "R", "wB": "B", "wN": "N", "wP": "P",
        "bK": "k", "bQ": "q", "bR": "r", "bB": "b", "bN": "n", "bP": "p",
    }

    def __init__(self, use_unicode: bool = True):
        self.use_unicode = use_unicode
        self.reset()

    def reset(self):
        self.board: list[list[str | None]] = self._init_board()
        self.turn: str = "w"   # "w" or "b"
        self.castling_rights: dict = {"wK": True, "wQ": True, "bK": True, "bQ": True}
        self.en_passant: tuple | None = None   # (row, col) or None
        self.move_history: list[str] = []
        self.captured: dict = {"w": [], "b": []}
        self.halfmove_clock: int = 0
        self.fullmove: int = 1
        self.game_over: bool = False
        self.result: str = ""

    def _init_board(self) -> list[list]:
        b = [[None] * 8 for _ in range(8)]
        order = ["R", "N", "B", "Q", "K", "B", "N", "R"]
        for c, p in enumerate(order):
            b[0][c] = f"b{p}"
            b[7][c] = f"w{p}"
        for c in range(8):
            b[1][c] = "bP"
            b[6][c] = "wP"
        return b

    def piece_symbol(self, piece: str) -> str:
        if self.use_unicode:
            return self.UNICODE_PIECES.get(piece, "?")
        return self.ASCII_PIECES.get(piece, "?")

    def board_str(self, highlight: list[tuple] = None) -> str:
        highlight = highlight or []
        hl_set = set(highlight)
        lines = []
        sep_line = "  +" + "---+" * 8
        col_labels = "    a   b   c   d   e   f   g   h"
        lines.append(col_labels)
        lines.append(sep_line)
        for r in range(8):
            row_num = 8 - r
            cells = []
            for c in range(8):
                piece = self.board[r][c]
                sym = self.piece_symbol(piece) if piece else " "
                if (r, c) in hl_set:
                    cells.append(f"\033[43m {sym} \033[0m")
                elif (r + c) % 2 == 0:
                    cells.append(f"\033[47m {sym} \033[0m")
                else:
                    cells.append(f"\033[100m {sym} \033[0m")
            lines.append(f"{row_num} |{'|'.join(cells)}|")
            lines.append(sep_line)
        lines.append(col_labels)
        return "\n".join(lines)

    def parse_sq(self, s: str) -> tuple | None:
        s = s.strip().lower()
        if len(s) != 2: return None
        c = ord(s[0]) - ord('a')
        r = 8 - int(s[1])
        if not (0 <= r <= 7 and 0 <= c <= 7): return None
        return (r, c)

    def sq_name(self, r: int, c: int) -> str:
        return chr(ord('a') + c) + str(8 - r)

    def _enemy(self, color: str) -> str:
        return "b" if color == "w" else "w"

    def _piece_color(self, piece: str | None) -> str | None:
        return piece[0] if piece else None

    def _piece_type(self, piece: str | None) -> str | None:
        return piece[1] if piece else None

    def _on_board(self, r: int, c: int) -> bool:
        return 0 <= r <= 7 and 0 <= c <= 7

    def pseudo_legal_moves(self, r: int, c: int) -> list[tuple]:
        piece = self.board[r][c]
        if not piece: return []
        color = piece[0]
        ptype = piece[1]
        moves = []

        if ptype == "P":
            moves = self._pawn_moves(r, c, color)
        elif ptype == "N":
            moves = self._knight_moves(r, c, color)
        elif ptype == "B":
            moves = self._sliding_moves(r, c, color, [(1,1),(1,-1),(-1,1),(-1,-1)])
        elif ptype == "R":
            moves = self._sliding_moves(r, c, color, [(1,0),(-1,0),(0,1),(0,-1)])
        elif ptype == "Q":
            moves = self._sliding_moves(r, c, color, [(1,1),(1,-1),(-1,1),(-1,-1),(1,0),(-1,0),(0,1),(0,-1)])
        elif ptype == "K":
            moves = self._king_moves(r, c, color)
        return moves

    def _pawn_moves(self, r: int, c: int, color: str) -> list[tuple]:
        moves = []
        d = -1 if color == "w" else 1
        start_row = 6 if color == "w" else 1
        # 前進
        nr = r + d
        if self._on_board(nr, c) and not self.board[nr][c]:
            moves.append((nr, c))
            # 初期2マス
            if r == start_row and not self.board[r + 2*d][c]:
                moves.append((r + 2*d, c))
        # 斜め攻撃
        for dc in (-1, 1):
            nc = c + dc
            if self._on_board(nr, nc):
                target = self.board[nr][nc]
                if target and target[0] != color:
                    moves.append((nr, nc))
                # アンパッサン
                if self.en_passant == (nr, nc):
                    moves.append((nr, nc))
        return moves

    def _knight_moves(self, r: int, c: int, color: str) -> list[tuple]:
        moves = []
        for dr, dc in [(-2,-1),(-2,1),(-1,-2),(-1,2),(1,-2),(1,2),(2,-1),(2,1)]:
            nr, nc = r+dr, c+dc
            if self._on_board(nr, nc):
                t = self.board[nr][nc]
                if not t or t[0] != color:
                    moves.append((nr, nc))
        return moves

    def _sliding_moves(self, r: int, c: int, color: str, dirs: list) -> list[tuple]:
        moves = []
        for dr, dc in dirs:
            nr, nc = r+dr, c+dc
            while self._on_board(nr, nc):
                t = self.board[nr][nc]
                if t:
                    if t[0] != color: moves.append((nr, nc))
                    break
                moves.append((nr, nc))
                nr += dr; nc += dc
        return moves

    def _king_moves(self, r: int, c: int, color: str) -> list[tuple]:
        moves = []
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0: continue
                nr, nc = r+dr, c+dc
                if self._on_board(nr, nc):
                    t = self.board[nr][nc]
                    if not t or t[0] != color:
                        moves.append((nr, nc))
        # キャスリング
        back_rank = 7 if color == "w" else 0
        if r == back_rank and c == 4:
            # キングサイド
            if self.castling_rights[f"{color}K"]:
                if (not self.board[back_rank][5] and not self.board[back_rank][6]
                        and self.board[back_rank][7] == f"{color}R"):
                    if not self._sq_attacked(back_rank, 4, self._enemy(color)) \
                            and not self._sq_attacked(back_rank, 5, self._enemy(color)) \
                            and not self._sq_attacked(back_rank, 6, self._enemy(color)):
                        moves.append((back_rank, 6))
            # クイーンサイド
            if self.castling_rights[f"{color}Q"]:
                if (not self.board[back_rank][3] and not self.board[back_rank][2]
                        and not self.board[back_rank][1]
                        and self.board[back_rank][0] == f"{color}R"):
                    if not self._sq_attacked(back_rank, 4, self._enemy(color)) \
                            and not self._sq_attacked(back_rank, 3, self._enemy(color)) \
                            and not self._sq_attacked(back_rank, 2, self._enemy(color)):
                        moves.append((back_rank, 2))
        return moves

    def _sq_attacked(self, r: int, c: int, by_color: str) -> bool:
        """by_color の駒が (r,c) を攻撃しているか"""
        enemy = by_color
        # ポーン攻撃
        pd = 1 if enemy == "w" else -1
        for dc in (-1, 1):
            nr, nc = r+pd, c+dc
            if self._on_board(nr, nc) and self.board[nr][nc] == f"{enemy}P":
                return True
        # ナイト
        for dr, dc in [(-2,-1),(-2,1),(-1,-2),(-1,2),(1,-2),(1,2),(2,-1),(2,1)]:
            nr, nc = r+dr, c+dc
            if self._on_board(nr, nc) and self.board[nr][nc] == f"{enemy}N":
                return True
        # 直線・斜め
        for dr, dc in [(1,0),(-1,0),(0,1),(0,-1)]:
            nr, nc = r+dr, c+dc
            while self._on_board(nr, nc):
                t = self.board[nr][nc]
                if t:
                    if t[0] == enemy and t[1] in ("R", "Q"): return True
                    break
                nr += dr; nc += dc
        for dr, dc in [(1,1),(1,-1),(-1,1),(-1,-1)]:
            nr, nc = r+dr, c+dc
            while self._on_board(nr, nc):
                t = self.board[nr][nc]
                if t:
                    if t[0] == enemy and t[1] in ("B", "Q"): return True
                    break
                nr += dr; nc += dc
        # キング
        for dr in (-1,0,1):
            for dc in (-1,0,1):
                if dr == 0 and dc == 0: continue
                nr, nc = r+dr, c+dc
                if self._on_board(nr, nc) and self.board[nr][nc] == f"{enemy}K":
                    return True
        return False

    def _find_king(self, color: str) -> tuple | None:
        for r in range(8):
            for c in range(8):
                if self.board[r][c] == f"{color}K":
                    return (r, c)
        return None

    def in_check(self, color: str) -> bool:
        kpos = self._find_king(color)
        if kpos is None: return False
        return self._sq_attacked(kpos[0], kpos[1], self._enemy(color))

    def _apply_move_temp(self, r: int, c: int, tr: int, tc: int) -> dict:
        """合法性チェックなしで仮に駒を動かし、undo用のsavedを返す (AI探索用)。"""
        piece = self.board[r][c]
        target = self.board[tr][tc]
        saved = {
            "from": (r, c, piece),
            "to": (tr, tc, target),
            "en_passant": self.en_passant,
            "castling_rights": dict(self.castling_rights),
            "halfmove_clock": self.halfmove_clock,
        }

        # アンパッサン捕獲
        ep_capture = None
        if piece and piece[1] == "P" and self.en_passant == (tr, tc):
            ep_r = tr + (1 if piece[0] == "w" else -1)
            ep_capture = (ep_r, tc, self.board[ep_r][tc])
            self.board[ep_r][tc] = None
        saved["ep_capture"] = ep_capture

        # キャスリング時ルーク移動
        rook_move = None
        if piece and piece[1] == "K" and abs(tc - c) == 2:
            back_rank = r
            if tc == 6:
                rook_move = (back_rank, 7, back_rank, 5, self.board[back_rank][7])
                self.board[back_rank][5] = self.board[back_rank][7]
                self.board[back_rank][7] = None
            elif tc == 2:
                rook_move = (back_rank, 0, back_rank, 3, self.board[back_rank][0])
                self.board[back_rank][3] = self.board[back_rank][0]
                self.board[back_rank][0] = None
        saved["rook_move"] = rook_move

        self.board[r][c] = None
        self.board[tr][tc] = piece

        # プロモーション (常にクイーンに昇格)
        if piece and piece[1] == "P" and (tr == 0 or tr == 7):
            self.board[tr][tc] = f"{piece[0]}Q"

        # アンパッサン更新
        self.en_passant = None
        if piece and piece[1] == "P" and abs(tr - r) == 2:
            self.en_passant = ((r + tr) // 2, c)

        # キャスリング権更新
        if piece and piece[1] == "K":
            color = piece[0]
            self.castling_rights[f"{color}K"] = False
            self.castling_rights[f"{color}Q"] = False
        if piece and piece[1] == "R":
            color = piece[0]
            back_rank = 7 if color == "w" else 0
            if r == back_rank and c == 7: self.castling_rights[f"{color}K"] = False
            if r == back_rank and c == 0: self.castling_rights[f"{color}Q"] = False

        return saved

    def legal_moves(self, color: str) -> list[tuple]:
        """(from_r, from_c, to_r, to_c) の合法手リスト"""
        result = []
        for r in range(8):
            for c in range(8):
                piece = self.board[r][c]
                if not piece or piece[0] != color: continue
                for tr, tc in self.pseudo_legal_moves(r, c):
                    saved = self._apply_move_temp(r, c, tr, tc)
                    if not self.in_check(color):
                        result.append((r, c, tr, tc))
                    self._undo_move_temp(saved)
        return result

    def _undo_move_temp(self, saved):
        r, c, piece = saved["from"]
        tr, tc, target = saved["to"]
        self.board[r][c] = piece
        self.board[tr][tc] = target
        self.en_passant = saved["en_passant"]
        self.castling_rights = saved["castling_rights"]
        if saved.get("ep_capture"):
            er, ec, ep = saved["ep_capture"]
            self.board[er][ec] = ep
        if saved.get("rook_move"):
            rr, rc, nrr, nrc, rp = saved["rook_move"]
            self.board[rr][rc] = rp
            self.board[nrr][nrc] = None

    def move_sq(self, r: int, c: int, tr: int, tc: int, promotion: str = "Q") -> tuple[bool, str]:
        """駒を移動する。成功時 (True, 棋譜表記)、失敗時 (False, エラー文字列)"""
        piece = self.board[r][c]
        if not piece:
            return False, "その位置に駒がありません"
        if piece[0] != self.turn:
            return False, f"{'白' if self.turn=='w' else '黒'}の手番です"
        legal = self.legal_moves(self.turn)
        if (r, c, tr, tc) not in legal:
            return False, "その手は合法ではありません"

        target = self.board[tr][tc]
        notation = self._build_notation(r, c, tr, tc, piece, target, promotion)

        # アンパッサン
        ep_capture_pos = None
        if piece[1] == "P" and self.en_passant == (tr, tc):
            ep_r = tr + (1 if piece[0] == "w" else -1)
            ep_capture_pos = (ep_r, tc)
            cap = self.board[ep_r][tc]
            if cap: self.captured[self.turn].append(cap)
            self.board[ep_r][tc] = None

        if target:
            self.captured[self.turn].append(target)

        self.board[r][c] = None
        self.board[tr][tc] = piece

        # キャスリング
        if piece[1] == "K":
            color = piece[0]
            back_rank = 7 if color == "w" else 0
            if tc == 6 and c == 4:
                self.board[back_rank][5] = self.board[back_rank][7]
                self.board[back_rank][7] = None
            elif tc == 2 and c == 4:
                self.board[back_rank][3] = self.board[back_rank][0]
                self.board[back_rank][0] = None
            self.castling_rights[f"{color}K"] = False
            self.castling_rights[f"{color}Q"] = False

        # ルーク移動 → キャスリング権失効
        if piece[1] == "R":
            color = piece[0]
            back_rank = 7 if color == "w" else 0
            if r == back_rank and c == 7: self.castling_rights[f"{color}K"] = False
            if r == back_rank and c == 0: self.castling_rights[f"{color}Q"] = False

        # アンパッサン設定
        self.en_passant = None
        if piece[1] == "P" and abs(tr - r) == 2:
            self.en_passant = ((r + tr) // 2, c)

        # プロモーション
        if piece[1] == "P" and (tr == 0 or tr == 7):
            self.board[tr][tc] = f"{piece[0]}{promotion}"
            notation += f"={promotion}"

        # チェック確認
        enemy = self._enemy(self.turn)
        check = self.in_check(enemy)
        self.turn = enemy
        if check:
            legal_next = self.legal_moves(self.turn)
            if not legal_next:
                notation += "#"
                self.game_over = True
                winner = "白" if self.turn == "b" else "黒"
                self.result = f"チェックメイト！{winner}の勝利"
            else:
                notation += "+"
        else:
            legal_next = self.legal_moves(self.turn)
            if not legal_next:
                notation += " (ステールメイト)"
                self.game_over = True
                self.result = "ステールメイト（引き分け）"

        self.move_history.append(notation)
        if self.turn == "w": self.fullmove += 1
        return True, notation

    def _build_notation(self, r, c, tr, tc, piece, target, promotion) -> str:
        ptype = piece[1]
        dest = self.sq_name(tr, tc)
        if ptype == "K" and abs(tc - c) == 2:
            return "O-O" if tc == 6 else "O-O-O"
        cap = "x" if target or (ptype == "P" and self.en_passant == (tr, tc)) else ""
        if ptype == "P":
            if cap:
                return f"{chr(ord('a')+c)}{cap}{dest}"
            return dest
        return f"{ptype}{cap}{dest}"

    def legal_targets(self, r: int, c: int) -> list[tuple]:
        """(r,c) の駒が動ける合法手の移動先リスト"""
        all_legal = self.legal_moves(self.turn)
        return [(tr, tc) for (fr, fc, tr, tc) in all_legal if fr == r and fc == c]

    def status_str(self) -> str:
        turn_str = "白(White)" if self.turn == "w" else "黒(Black)"
        check_str = " 【チェック！】" if self.in_check(self.turn) else ""
        cap_w = " ".join(self.piece_symbol(p) for p in self.captured["w"]) or "なし"
        cap_b = " ".join(self.piece_symbol(p) for p in self.captured["b"]) or "なし"
        move_count = (self.fullmove - 1) * 2 + (0 if self.turn == "w" else 1)
        hist = "  ".join(self.move_history[-6:]) if self.move_history else "なし"
        lines = [
            f"手番: {turn_str}{check_str}   ({move_count}手目)",
            f"白が取った駒: {cap_b}   黒が取った駒: {cap_w}",
            f"直近の手: {hist}",
        ]
        return "\n".join(lines)



# ===== チェス AI エンジン =====
import random

class ChessAI:
    """
    チェスAI。4段階の難易度に対応。
      easy      : ランダム手
      middle    : depth=1 minimax + 基本評価
      hard      : depth=3 minimax + alpha-beta + 評価関数
      very_hard : depth=4 minimax + alpha-beta + 評価関数 + ランダム揺らぎなし
    """

    # 駒の基本価値
    PIECE_VALUE = {"P": 100, "N": 320, "B": 330, "R": 500, "Q": 900, "K": 20000}

    # 駒ごとのポジションボーナス (白視点, 行0=黒側, 行7=白側)
    _PST = {
        "P": [
            [ 0,  0,  0,  0,  0,  0,  0,  0],
            [50, 50, 50, 50, 50, 50, 50, 50],
            [10, 10, 20, 30, 30, 20, 10, 10],
            [ 5,  5, 10, 25, 25, 10,  5,  5],
            [ 0,  0,  0, 20, 20,  0,  0,  0],
            [ 5, -5,-10,  0,  0,-10, -5,  5],
            [ 5, 10, 10,-20,-20, 10, 10,  5],
            [ 0,  0,  0,  0,  0,  0,  0,  0],
        ],
        "N": [
            [-50,-40,-30,-30,-30,-30,-40,-50],
            [-40,-20,  0,  0,  0,  0,-20,-40],
            [-30,  0, 10, 15, 15, 10,  0,-30],
            [-30,  5, 15, 20, 20, 15,  5,-30],
            [-30,  0, 15, 20, 20, 15,  0,-30],
            [-30,  5, 10, 15, 15, 10,  5,-30],
            [-40,-20,  0,  5,  5,  0,-20,-40],
            [-50,-40,-30,-30,-30,-30,-40,-50],
        ],
        "B": [
            [-20,-10,-10,-10,-10,-10,-10,-20],
            [-10,  0,  0,  0,  0,  0,  0,-10],
            [-10,  0,  5, 10, 10,  5,  0,-10],
            [-10,  5,  5, 10, 10,  5,  5,-10],
            [-10,  0, 10, 10, 10, 10,  0,-10],
            [-10, 10, 10, 10, 10, 10, 10,-10],
            [-10,  5,  0,  0,  0,  0,  5,-10],
            [-20,-10,-10,-10,-10,-10,-10,-20],
        ],
        "R": [
            [ 0,  0,  0,  0,  0,  0,  0,  0],
            [ 5, 10, 10, 10, 10, 10, 10,  5],
            [-5,  0,  0,  0,  0,  0,  0, -5],
            [-5,  0,  0,  0,  0,  0,  0, -5],
            [-5,  0,  0,  0,  0,  0,  0, -5],
            [-5,  0,  0,  0,  0,  0,  0, -5],
            [-5,  0,  0,  0,  0,  0,  0, -5],
            [ 0,  0,  0,  5,  5,  0,  0,  0],
        ],
        "Q": [
            [-20,-10,-10, -5, -5,-10,-10,-20],
            [-10,  0,  0,  0,  0,  0,  0,-10],
            [-10,  0,  5,  5,  5,  5,  0,-10],
            [ -5,  0,  5,  5,  5,  5,  0, -5],
            [  0,  0,  5,  5,  5,  5,  0, -5],
            [-10,  5,  5,  5,  5,  5,  0,-10],
            [-10,  0,  5,  0,  0,  0,  0,-10],
            [-20,-10,-10, -5, -5,-10,-10,-20],
        ],
        "K": [
            [-30,-40,-40,-50,-50,-40,-40,-30],
            [-30,-40,-40,-50,-50,-40,-40,-30],
            [-30,-40,-40,-50,-50,-40,-40,-30],
            [-30,-40,-40,-50,-50,-40,-40,-30],
            [-20,-30,-30,-40,-40,-30,-30,-20],
            [-10,-20,-20,-20,-20,-20,-20,-10],
            [ 20, 20,  0,  0,  0,  0, 20, 20],
            [ 20, 30, 10,  0,  0, 10, 30, 20],
        ],
    }

    DIFFICULTY_SETTINGS = {
        "easy":      {"depth": 0, "random_rate": 1.0},   # 完全ランダム
        "middle":    {"depth": 1, "random_rate": 0.2},   # depth1 + 20%ランダム
        "hard":      {"depth": 3, "random_rate": 0.0},   # depth3 alpha-beta
        "very_hard": {"depth": 4, "random_rate": 0.0},   # depth4 alpha-beta
    }

    def __init__(self, difficulty: str = "middle", color: str = "b"):
        self.difficulty = difficulty
        self.color = color  # AIが担当する色 ("w" or "b")
        s = self.DIFFICULTY_SETTINGS.get(difficulty, self.DIFFICULTY_SETTINGS["middle"])
        self.depth = s["depth"]
        self.random_rate = s["random_rate"]

    def _pst_score(self, piece: str, r: int, c: int) -> int:
        """駒のポジションスコア (白視点)"""
        color, ptype = piece[0], piece[1]
        table = self._PST.get(ptype)
        if table is None:
            return 0
        if color == "w":
            return table[r][c]
        else:
            return table[7 - r][c]

    def evaluate(self, g: "ChessEngine") -> int:
        """盤面評価 (正=白有利, 負=黒有利)"""
        score = 0
        for r in range(8):
            for c in range(8):
                piece = g.board[r][c]
                if not piece:
                    continue
                color, ptype = piece[0], piece[1]
                val = self.PIECE_VALUE.get(ptype, 0) + self._pst_score(piece, r, c)
                score += val if color == "w" else -val
        return score

    def _all_legal_moves(self, g: "ChessEngine", color: str) -> list[tuple]:
        return g.legal_moves(color)

    def _minimax(self, g: "ChessEngine", depth: int, alpha: int, beta: int, maximizing: bool) -> int:
        if depth == 0 or g.game_over:
            return self.evaluate(g)

        color = "w" if maximizing else "b"
        moves = self._all_legal_moves(g, color)
        if not moves:
            return self.evaluate(g)

        if maximizing:
            best = -10**9
            for fr, fc, tr, tc in moves:
                saved = g._apply_move_temp(fr, fc, tr, tc)
                prev_turn = g.turn
                g.turn = "b"
                val = self._minimax(g, depth - 1, alpha, beta, False)
                g.turn = prev_turn
                g._undo_move_temp(saved)
                best = max(best, val)
                alpha = max(alpha, val)
                if beta <= alpha:
                    break
            return best
        else:
            best = 10**9
            for fr, fc, tr, tc in moves:
                saved = g._apply_move_temp(fr, fc, tr, tc)
                prev_turn = g.turn
                g.turn = "w"
                val = self._minimax(g, depth - 1, alpha, beta, True)
                g.turn = prev_turn
                g._undo_move_temp(saved)
                best = min(best, val)
                beta = min(beta, val)
                if beta <= alpha:
                    break
            return best

    def choose_move(self, g: "ChessEngine") -> tuple | None:
        """AIが次の手を選んで (fr, fc, tr, tc) を返す。手がなければ None。"""
        moves = self._all_legal_moves(g, self.color)
        if not moves:
            return None

        # easy: 完全ランダム
        if self.difficulty == "easy":
            return random.choice(moves)

        # middle/hard/very_hard: random_rate の確率でランダム手
        if self.random_rate > 0 and random.random() < self.random_rate:
            return random.choice(moves)

        # minimax で最善手を探す
        maximizing = (self.color == "w")
        best_val = -10**9 if maximizing else 10**9
        best_moves = []

        for fr, fc, tr, tc in moves:
            saved = g._apply_move_temp(fr, fc, tr, tc)
            prev_turn = g.turn
            g.turn = "b" if self.color == "w" else "w"
            val = self._minimax(g, self.depth - 1, -10**9, 10**9, not maximizing)
            g.turn = prev_turn
            g._undo_move_temp(saved)

            if maximizing:
                if val > best_val:
                    best_val = val
                    best_moves = [(fr, fc, tr, tc)]
                elif val == best_val:
                    best_moves.append((fr, fc, tr, tc))
            else:
                if val < best_val:
                    best_val = val
                    best_moves = [(fr, fc, tr, tc)]
                elif val == best_val:
                    best_moves.append((fr, fc, tr, tc))

        return random.choice(best_moves) if best_moves else random.choice(moves)


# ===== チェス curses マウス UI =====
import curses

# ── レイアウト定数 ──────────────────────────────────────────
_CW   = 5   # マス幅 (chars)  ← Unicode駒の表示幅を考慮
_CH   = 3   # マス高 (lines)
_BX   = 4   # 盤面左端 (col offset) ← 行番号 "8 " 分
_BY   = 2   # 盤面上端 (row offset) ← タイトル分
_INFO_X = _BX + _CW * 8 + 2   # 右パネル開始列

# ── カラーペア ID ────────────────────────────────────────────
_CP_LIGHT       = 1   # 白マス
_CP_DARK        = 2   # 黒マス
_CP_SELECTED    = 3   # 選択中マス
_CP_LEGAL       = 4   # 合法手マス
_CP_LAST_MOVE   = 5   # 直前の移動元/先
_CP_CHECK       = 6   # チェック中のキング
_CP_TITLE       = 7   # タイトルバー
_CP_PANEL       = 8   # 右パネル
_CP_BTN         = 9   # ボタン通常
_CP_BTN_HL      = 10  # ボタンハイライト
_CP_STATUS_OK   = 11  # ステータス (通常)
_CP_STATUS_WARN = 12  # ステータス (警告)
_CP_PROMO       = 13  # プロモーションポップ
_CP_COMMENT     = 14  # ペルソナテロップ

def _init_colors():
    curses.start_color()
    curses.use_default_colors()
    # light squares: dark text on cream
    curses.init_pair(_CP_LIGHT,       curses.COLOR_BLACK,   curses.COLOR_WHITE)
    # dark squares: white text on dark green
    curses.init_pair(_CP_DARK,        curses.COLOR_WHITE,   curses.COLOR_GREEN)
    # selected: black on yellow
    curses.init_pair(_CP_SELECTED,    curses.COLOR_BLACK,   curses.COLOR_YELLOW)
    # legal move dot: black on cyan
    curses.init_pair(_CP_LEGAL,       curses.COLOR_BLACK,   curses.COLOR_CYAN)
    # last move: black on blue
    curses.init_pair(_CP_LAST_MOVE,   curses.COLOR_WHITE,   curses.COLOR_BLUE)
    # check: white on red
    curses.init_pair(_CP_CHECK,       curses.COLOR_WHITE,   curses.COLOR_RED)
    # title bar: black on white
    curses.init_pair(_CP_TITLE,       curses.COLOR_BLACK,   curses.COLOR_WHITE)
    # right panel: white on black (default)
    curses.init_pair(_CP_PANEL,       curses.COLOR_WHITE,   -1)
    # button
    curses.init_pair(_CP_BTN,         curses.COLOR_BLACK,   curses.COLOR_WHITE)
    curses.init_pair(_CP_BTN_HL,      curses.COLOR_WHITE,   curses.COLOR_MAGENTA)
    # status bar
    curses.init_pair(_CP_STATUS_OK,   curses.COLOR_BLACK,   curses.COLOR_CYAN)
    curses.init_pair(_CP_STATUS_WARN, curses.COLOR_WHITE,   curses.COLOR_RED)
    # promotion popup
    curses.init_pair(_CP_PROMO,       curses.COLOR_BLACK,   curses.COLOR_YELLOW)
    curses.init_pair(_CP_COMMENT,     curses.COLOR_BLACK,   curses.COLOR_MAGENTA)  # テロップ


def _chess_curses_main(stdscr, g: "ChessEngine", ai: "ChessAI | None" = None,
                       commentator: "GameCommentator | None" = None):
    """curses ループ本体。マウスクリックでチェスを操作する。"""
    _init_colors()
    curses.curs_set(0)
    curses.mousemask(curses.ALL_MOUSE_EVENTS | curses.REPORT_MOUSE_POSITION)
    curses.mouseinterval(0)
    stdscr.keypad(True)
    stdscr.timeout(80)   # ms – リフレッシュ間隔

    selected: tuple | None = None       # 選択中マス (r, c)
    legal_tgts: list[tuple] = []        # 現選択駒の合法手
    last_move: list[tuple] = []         # 直前の移動元/先

    # AI難易度ラベル
    _diff_labels = {"easy": "Easy", "middle": "Middle", "hard": "Hard", "very_hard": "Very Hard"}
    if ai:
        ai_label = _diff_labels.get(ai.difficulty, ai.difficulty)
        status_msg = f"♟ AI対戦モード [{ai_label}] — 白(あなた)から開始。駒をクリック！"
    else:
        status_msg = "♟ クリックして駒を選択してください"
    status_warn = False
    undo_stack: list[dict] = []
    promo_pending: tuple | None = None  # (fr, fc, tr, tc) プロモーション待ち

    # ── ボタン定義 [(ラベル, action_key), ...] ─────────────────
    BUTTONS = [
        ("  New  ", "new"),
        ("  Undo ", "undo"),
        ("  Quit ", "quit"),
    ]

    def _snapshot():
        return {
            "board": [row[:] for row in g.board],
            "turn": g.turn,
            "castling_rights": dict(g.castling_rights),
            "en_passant": g.en_passant,
            "move_history": g.move_history[:],
            "captured": {"w": g.captured["w"][:], "b": g.captured["b"][:]},
            "fullmove": g.fullmove,
            "game_over": g.game_over,
            "result": g.result,
        }

    def _restore(snap):
        g.board            = snap["board"]
        g.turn             = snap["turn"]
        g.castling_rights  = snap["castling_rights"]
        g.en_passant       = snap["en_passant"]
        g.move_history     = snap["move_history"]
        g.captured         = snap["captured"]
        g.fullmove         = snap["fullmove"]
        g.game_over        = snap["game_over"]
        g.result           = snap["result"]

    def _sq_to_screen(r, c):
        """ボードマス (r, c) → curses 左上 (y, x)"""
        return (_BY + r * _CH, _BX + c * _CW)

    def _screen_to_sq(my, mx):
        """curses 座標 → ボードマス (r, c) or None"""
        r = (my - _BY) // _CH
        c = (mx - _BX) // _CW
        if 0 <= r <= 7 and 0 <= c <= 7:
            ry = my - (_BY + r * _CH)
            rx = mx - (_BX + c * _CW)
            if 0 <= ry < _CH and 0 <= rx < _CW:
                return (r, c)
        return None

    def _draw_cell(r, c, piece, color_pair, center_mark=""):
        """1マスを描画 (_CH lines × _CW cols)"""
        sy, sx = _sq_to_screen(r, c)
        sym = g.piece_symbol(piece) if piece else " "
        # 上段・下段: 空白
        try:
            stdscr.addstr(sy,       sx, " " * _CW, curses.color_pair(color_pair))
            stdscr.addstr(sy + 2,   sx, " " * _CW, curses.color_pair(color_pair))
            # 中段: 駒シンボル
            mid = center_mark if (not piece and center_mark) else sym
            line = f"  {mid}  " if len(mid) == 1 else f" {mid}  "
            line = line[:_CW]
            stdscr.addstr(sy + 1, sx, line, curses.color_pair(color_pair) | curses.A_BOLD)
        except curses.error:
            pass

    def _draw_board():
        king_pos = g._find_king(g.turn)
        in_chk   = g.in_check(g.turn)

        for r in range(8):
            for c in range(8):
                piece = g.board[r][c]
                base_light = (r + c) % 2 == 0

                if selected and (r, c) == selected:
                    cp = _CP_SELECTED
                elif (r, c) in legal_tgts:
                    cp = _CP_LEGAL
                elif (r, c) in last_move:
                    cp = _CP_LAST_MOVE
                elif in_chk and king_pos and (r, c) == king_pos:
                    cp = _CP_CHECK
                else:
                    cp = _CP_LIGHT if base_light else _CP_DARK

                mark = "·" if (r, c) in legal_tgts and not piece else ""
                _draw_cell(r, c, piece, cp, center_mark=mark)

        # 行ラベル (8〜1)
        for r in range(8):
            sy, _ = _sq_to_screen(r, 0)
            try:
                stdscr.addstr(sy + 1, _BX - 2, str(8 - r),
                              curses.color_pair(_CP_PANEL) | curses.A_BOLD)
            except curses.error:
                pass

        # 列ラベル (a〜h)
        col_y = _BY + 8 * _CH
        for c in range(8):
            _, sx = _sq_to_screen(0, c)
            try:
                stdscr.addstr(col_y, sx + 2, chr(ord('a') + c),
                              curses.color_pair(_CP_PANEL) | curses.A_BOLD)
            except curses.error:
                pass

    def _draw_title():
        turn_str = "♔ 白 (White)" if g.turn == "w" else "♚ 黒 (Black)"
        chk_str  = "  ⚠ チェック！" if g.in_check(g.turn) else ""
        move_n   = (g.fullmove - 1) * 2 + (0 if g.turn == "w" else 1)
        _diff_labels = {"easy": "Easy", "middle": "Middle", "hard": "Hard", "very_hard": "Very Hard"}
        ai_str = f"  [AI:{_diff_labels.get(ai.difficulty,'')}]" if ai else ""
        title = f"  ♟ チェス{ai_str}  {turn_str}{chk_str}   {move_n}手目  "
        try:
            stdscr.addstr(0, 0, title.ljust(80), curses.color_pair(_CP_TITLE) | curses.A_BOLD)
        except curses.error:
            pass

    def _draw_panel():
        """右パネル: 取得駒 / 手の記録 / ボタン"""
        px = _INFO_X
        h, w = stdscr.getmaxyx()

        # 取得駒
        cap_b_sym = " ".join(g.piece_symbol(p) for p in g.captured["w"][-8:]) or "なし"
        cap_w_sym = " ".join(g.piece_symbol(p) for p in g.captured["b"][-8:]) or "なし"
        try:
            stdscr.addstr(_BY,     px, "取:白→ " + cap_b_sym, curses.color_pair(_CP_PANEL))
            stdscr.addstr(_BY + 1, px, "取:黒→ " + cap_w_sym, curses.color_pair(_CP_PANEL))
        except curses.error:
            pass

        # 棋譜
        hist_y = _BY + 3
        try:
            stdscr.addstr(hist_y - 1, px, "── 棋譜 ──────────",
                          curses.color_pair(_CP_PANEL) | curses.A_DIM)
        except curses.error:
            pass
        hist = g.move_history
        panel_h = max(4, h - hist_y - 6)
        start_i = max(0, len(hist) - panel_h * 2)
        line_i  = 0
        for i in range(start_i, len(hist), 2):
            w_m = hist[i] if i < len(hist) else ""
            b_m = hist[i + 1] if i + 1 < len(hist) else ""
            num = i // 2 + 1
            line = f"{num:2d}. {w_m:<8s} {b_m}"
            try:
                stdscr.addstr(hist_y + line_i, px, line[:28], curses.color_pair(_CP_PANEL))
            except curses.error:
                pass
            line_i += 1
            if line_i >= panel_h:
                break

        # ボタン
        btn_y = h - 4
        btn_x = px
        _draw_buttons(btn_y, btn_x)

    def _draw_buttons(by, bx):
        for i, (label, _) in enumerate(BUTTONS):
            try:
                stdscr.addstr(by, bx + i * 10, label,
                              curses.color_pair(_CP_BTN) | curses.A_BOLD)
            except curses.error:
                pass

    def _btn_at(my, mx):
        """クリック座標がボタンに当たっていれば action_key を返す"""
        h, _ = stdscr.getmaxyx()
        by = h - 4
        bx = _INFO_X
        for i, (label, action) in enumerate(BUTTONS):
            lx = bx + i * 10
            if my == by and lx <= mx < lx + len(label):
                return action
        return None

    def _draw_status(msg, warn=False):
        h, w_max = stdscr.getmaxyx()
        cp = _CP_STATUS_WARN if warn else _CP_STATUS_OK
        line = f"  {msg}  "
        try:
            stdscr.addstr(h - 2, 0, line.ljust(w_max - 1), curses.color_pair(cp))
        except curses.error:
            pass

    def _draw_promotion_popup(color: str):
        """プロモーション選択ポップアップを描画し、クリック位置を返す"""
        pieces = [f"{color}Q", f"{color}R", f"{color}B", f"{color}N"]
        labels = ["クイーン", "ルーク", "ビショップ", "ナイト"]
        h, w_max = stdscr.getmaxyx()
        pw, ph = 52, 7
        py = h // 2 - ph // 2
        px_ = w_max // 2 - pw // 2

        cp = curses.color_pair(_CP_PROMO) | curses.A_BOLD
        try:
            stdscr.addstr(py,     px_, "╔" + "═"*(pw-2) + "╗", cp)
            stdscr.addstr(py + 1, px_, "║" + "  プロモーション駒を選んでクリック  ".center(pw-2) + "║", cp)
            stdscr.addstr(py + 2, px_, "║" + " " * (pw-2) + "║", cp)
            for i, (p, lbl) in enumerate(zip(pieces, labels)):
                sym = g.piece_symbol(p)
                cell = f" {sym} {lbl} "
                bx_ = px_ + 1 + i * 12
                stdscr.addstr(py + 3, bx_, cell.ljust(11), cp)
            stdscr.addstr(py + 4, px_, "║" + " " * (pw-2) + "║", cp)
            stdscr.addstr(py + 5, px_, "║" + "   (クリック or Q/R/B/N キー)   ".center(pw-2) + "║", cp)
            stdscr.addstr(py + 6, px_, "╚" + "═"*(pw-2) + "╝", cp)
        except curses.error:
            pass
        stdscr.refresh()

        # promo ボタン領域を返す: [(piece, y, x_start, x_end), ...]
        zones = []
        for i, p in enumerate(pieces):
            bx_ = px_ + 1 + i * 12
            zones.append((p[1], py + 3, bx_, bx_ + 11))
        return zones

    def _do_move(fr, fc, tr, tc, promotion="Q"):
        nonlocal selected, legal_tgts, last_move, status_msg, status_warn
        snap = _snapshot()
        # 評価値の変化でコメント種別を決定
        piece_before = g.board[fr][fc] if fr is not None else None
        target_before = g.board[tr][tc] if g.board[tr][tc] else None
        ok, msg = g.move_sq(fr, fc, tr, tc, promotion)
        if ok:
            undo_stack.append(snap)
            if len(undo_stack) > 60: undo_stack.pop(0)
            last_move = [(fr, fc), (tr, tc)]
            selected  = None
            legal_tgts = []
            status_msg  = f"✔ {msg}"
            status_warn = False
            # ── コメンタートリガー ──────────────────────────
            if commentator:
                in_chk = g.in_check(g.turn)
                is_capture = target_before is not None
                is_promo = promotion and piece_before and piece_before[1] == "P"
                if g.game_over:
                    commentator.trigger("ゲームセット", f"結果: {g.result}")
                elif in_chk:
                    commentator.trigger("チェック", f"{msg} — チェック！")
                elif is_promo:
                    commentator.trigger("ポーンがプロモーション", f"{msg}")
                elif is_capture:
                    commentator.trigger("駒を取った", f"{msg}")
                else:
                    if _rnd_chess.random() < 0.3:
                        commentator.trigger("指し手", f"{msg} ({len(g.move_history)}手目)")
            # ────────────────────────────────────────────────
            if g.game_over:
                status_msg  = f"🏆 {g.result}"
                status_warn = True
        else:
            status_msg  = f"✖ {msg}"
            status_warn = True
        return ok

    def _draw_telop_chess():
        """ペルソナのテロップを最下行に表示（チェス版）"""
        if commentator is None:
            return
        h, w_max = stdscr.getmaxyx()
        lines = commentator.get_lines()
        if not lines:
            return
        text = lines[-1]
        try:
            stdscr.addstr(h - 1, 0, f" ♟ {text} ".ljust(w_max - 1),
                          curses.color_pair(_CP_COMMENT) | curses.A_BOLD)
        except curses.error:
            pass

    def _redraw():
        stdscr.erase()
        _draw_title()
        _draw_board()
        _draw_panel()
        _draw_status(status_msg, status_warn)
        _draw_telop_chess()
        stdscr.refresh()

    # ── メインループ ──────────────────────────────────────────
    import random as _rnd_chess
    _diff_labels_chess = {"easy": "Easy", "middle": "Middle", "hard": "Hard", "very_hard": "Very Hard"}
    _chess_ai_thread: threading.Thread | None = None
    _chess_ai_result: list = []

    def _chess_ai_think_bg():
        try:
            mv = ai.choose_move(g)
            _chess_ai_result.clear()
            if mv:
                _chess_ai_result.append(mv)
        except Exception:
            _chess_ai_result.clear()

    while True:
        # AI手番の処理（バックグラウンドスレッド）
        if ai and not g.game_over and g.turn == ai.color and not promo_pending:
            if _chess_ai_thread is None or not _chess_ai_thread.is_alive():
                if _chess_ai_result:
                    # 思考完了 → 着手
                    ai_move = _chess_ai_result[0]
                    _chess_ai_result.clear()
                    _chess_ai_thread = None
                    fr, fc, tr, tc = ai_move
                    snap = _snapshot()
                    ok, msg = g.move_sq(fr, fc, tr, tc)
                    if ok:
                        undo_stack.append(snap)
                        if len(undo_stack) > 60: undo_stack.pop(0)
                        last_move = [(fr, fc), (tr, tc)]
                        selected  = None
                        legal_tgts = []
                        status_msg = f"AI [{_diff_labels_chess.get(ai.difficulty,'')}]: {msg}"
                        status_warn = False
                        if g.game_over:
                            status_msg  = f"🏆 {g.result}"
                            status_warn = True
                        if commentator:
                            in_chk = g.in_check(g.turn)
                            if g.game_over:
                                commentator.trigger("AIが勝利", f"結果: {g.result}")
                            elif in_chk:
                                commentator.trigger("AIがチェック", f"AI: {msg}")
                            elif _rnd_chess.random() < 0.4:
                                commentator.trigger("AIの指し手", f"AI: {msg}")
                else:
                    # 思考スレッド起動
                    _chess_ai_result.clear()
                    status_msg = f"AI [{_diff_labels_chess.get(ai.difficulty,'')}] 思考中..."
                    status_warn = False
                    _chess_ai_thread = threading.Thread(target=_chess_ai_think_bg, daemon=True)
                    _chess_ai_thread.start()
            _redraw()
            stdscr.timeout(80)
            stdscr.getch()
            continue

        _redraw()

        # プロモーション待ち状態のとき専用ループ
        if promo_pending:
            fr, fc, tr, tc = promo_pending
            zones = _draw_promotion_popup(g.board[tr][tc][0] if g.board[tr][tc] else
                                          ("w" if (tr == 0) else "b"))
            # ポップアップ中だけ入力を待つ
            while True:
                key = stdscr.getch()
                if key in (ord('q'), ord('Q')): prom = "Q"; break
                if key in (ord('r'), ord('R')): prom = "R"; break
                if key in (ord('b'), ord('B')): prom = "B"; break
                if key in (ord('n'), ord('N')): prom = "N"; break
                if key == curses.KEY_MOUSE:
                    try:
                        _, mx, my, _, bstate = curses.getmouse()
                        if bstate & curses.BUTTON1_CLICKED or bstate & curses.BUTTON1_PRESSED:
                            for ptype, zy, zx0, zx1 in zones:
                                if my == zy and zx0 <= mx < zx1:
                                    prom = ptype
                                    break
                            else:
                                continue
                            break
                    except curses.error:
                        continue
            # promotion確定: ターンを一時的に修正して打つ
            # g.board[tr][tc] はすでに駒があるかもしれないので promo_pending 時のボードを使う
            # 実際には promo_pending 時点でまだ move_sq を呼んでいないので普通に呼ぶ
            promo_pending = None
            _do_move(fr, fc, tr, tc, prom)
            _redraw()
            continue

        key = stdscr.getch()

        if key == curses.KEY_MOUSE:
            try:
                _, mx, my, _, bstate = curses.getmouse()
            except curses.error:
                continue

            if not (bstate & curses.BUTTON1_CLICKED or bstate & curses.BUTTON1_PRESSED):
                continue

            # ボタン判定
            action = _btn_at(my, mx)
            if action == "quit":
                return "チェス終了"
            if action == "new":
                g.reset()
                undo_stack.clear()
                selected   = None
                legal_tgts = []
                last_move  = []
                _diff_labels = {"easy": "Easy", "middle": "Middle", "hard": "Hard", "very_hard": "Very Hard"}
                ai_str = f"[AI:{_diff_labels.get(ai.difficulty,'')}] " if ai else ""
                status_msg  = f"新しいゲームを開始しました {ai_str}"
                status_warn = False
                continue
            if action == "undo":
                if undo_stack:
                    _restore(undo_stack.pop())
                    selected   = None
                    legal_tgts = []
                    last_move  = []
                    status_msg  = "1手戻しました"
                    status_warn = False
                else:
                    status_msg  = "戻せる手がありません"
                    status_warn = True
                continue

            # マス判定
            sq = _screen_to_sq(my, mx)
            if sq is None:
                continue

            r, c = sq

            if g.game_over:
                status_msg  = f"ゲーム終了: {g.result}  (New で新ゲーム)"
                status_warn = True
                continue

            if selected is None:
                # 駒を選択
                piece = g.board[r][c]
                # AIモード: 相手の駒は動かせない
                if ai and piece and piece[0] == ai.color:
                    status_msg  = f"それはAIの駒です"
                    status_warn = True
                elif piece and piece[0] == g.turn:
                    targets = g.legal_targets(r, c)
                    if targets:
                        selected   = (r, c)
                        legal_tgts = targets
                        pname = {"K":"キング","Q":"クイーン","R":"ルーク",
                                  "B":"ビショップ","N":"ナイト","P":"ポーン"}.get(piece[1], piece[1])
                        status_msg  = f"選択: {g.sq_name(r,c)} ({pname})  — 移動先をクリック"
                        status_warn = False
                    else:
                        status_msg  = f"{g.sq_name(r,c)} の駒は動けません"
                        status_warn = True
                elif piece and piece[0] != g.turn:
                    status_msg  = f"{'白' if g.turn=='w' else '黒'}の手番です"
                    status_warn = True
                else:
                    status_msg  = "その位置に駒がありません"
                    status_warn = True
            else:
                fr, fc = selected
                if (r, c) == selected:
                    # 同じマスをクリック → 選択解除
                    selected   = None
                    legal_tgts = []
                    status_msg  = "選択を解除しました"
                    status_warn = False
                elif (r, c) in legal_tgts:
                    # 合法手マスへ移動
                    piece = g.board[fr][fc]
                    # プロモーション?
                    if piece and piece[1] == "P" and (r == 0 or r == 7):
                        promo_pending = (fr, fc, r, c)
                        status_msg  = "プロモーション駒をクリックして選択"
                        status_warn = False
                    else:
                        _do_move(fr, fc, r, c)
                elif g.board[r][c] and g.board[r][c][0] == g.turn:
                    # 別の自駒をクリック → 選択し直し
                    targets = g.legal_targets(r, c)
                    if targets:
                        selected   = (r, c)
                        legal_tgts = targets
                        pname = {"K":"キング","Q":"クイーン","R":"ルーク",
                                  "B":"ビショップ","N":"ナイト","P":"ポーン"}.get(g.board[r][c][1], "")
                        status_msg  = f"選択変更: {g.sq_name(r,c)} ({pname})"
                        status_warn = False
                    else:
                        selected = None; legal_tgts = []
                else:
                    # 合法手外をクリック → 選択解除
                    selected   = None
                    legal_tgts = []
                    status_msg  = "合法手ではありません。別の駒を選んでください"
                    status_warn = True

        elif key in (ord('q'), ord('Q'), 27):   # q / ESC
            return "チェス終了"
        elif key in (ord('n'), ord('N')):
            g.reset()
            undo_stack.clear()
            selected = None; legal_tgts = []; last_move = []
            _diff_labels = {"easy": "Easy", "middle": "Middle", "hard": "Hard", "very_hard": "Very Hard"}
            ai_str = f"[AI:{_diff_labels.get(ai.difficulty,'')}] " if ai else ""
            status_msg = f"新しいゲームを開始しました {ai_str}"; status_warn = False
        elif key in (ord('u'), ord('U')):
            if undo_stack:
                _restore(undo_stack.pop())
                selected = None; legal_tgts = []; last_move = []
                status_msg = "1手戻しました"; status_warn = False
            else:
                status_msg = "戻せる手がありません"; status_warn = True


_CHESS_GAME: "ChessEngine | None" = None

def handle_chess(arg: str, persona: dict | None = None) -> str:
    """チェスゲームのエントリポイント。/chess [easy|middle|hard|very_hard] で起動。"""
    global _CHESS_GAME
    arg = arg.strip().lower()

    # 難易度キーワードを解析
    difficulty_map = {
        "easy": "easy", "イージー": "easy", "簡単": "easy",
        "middle": "middle", "ミドル": "middle", "普通": "middle", "normal": "middle",
        "hard": "hard", "ハード": "hard", "難しい": "hard",
        "very_hard": "very_hard", "veryhard": "very_hard", "最難関": "very_hard",
        "very hard": "very_hard", "超難": "very_hard",
    }
    ai_difficulty = None
    for key, val in difficulty_map.items():
        if key in arg:
            ai_difficulty = val
            break

    if _CHESS_GAME is None or "new" in arg or ai_difficulty is not None:
        _CHESS_GAME = ChessEngine(use_unicode=True)

    ai = ChessAI(difficulty=ai_difficulty, color="b") if ai_difficulty else None
    # ペルソナコメンタータ生成
    _persona = persona or {"name": "プラトン", "style": "格調高い哲学者口調", "first_person": "私"}
    commentator = GameCommentator(_persona, game_kind="チェス")

    try:
        result = curses.wrapper(_chess_curses_main, _CHESS_GAME, ai, commentator)
    except Exception as e:
        return f"\033[31mチェス起動エラー: {e}\033[0m"
    return f"\033[32m{result or 'チェスを終了しました'}\033[0m"

# ===== 将棋エンジン =====

class ShogiEngine:
    """
    本将棋エンジン。
    - 9×9盤、先手(s)/後手(g)
    - 全駒種の移動・成り・打ち駒
    - 王手検出・合法手生成（王手放置禁止）
    - 二歩禁止・打ち歩詰め禁止
    - 棋譜記録
    """

    # 駒種定数 (先手: 大文字, 後手: 小文字)
    # FU=歩 KY=香 KE=桂 GI=銀 KI=金 KA=角 HI=飛 OU=王
    # +FU=と +KY=成香 +KE=成桂 +GI=成銀 +KA=馬 +HI=龍
    SENTE = "s"
    GOTE  = "g"

    PIECE_NAMES_JA = {
        "FU":"歩", "KY":"香", "KE":"桂", "GI":"銀", "KI":"金",
        "KA":"角", "HI":"飛", "OU":"王",
        "+FU":"と", "+KY":"成香", "+KE":"成桂", "+GI":"成銀",
        "+KA":"馬", "+HI":"龍",
    }
    PIECE_SYMBOLS = {
        "s": {
            "FU":"歩","KY":"香","KE":"桂","GI":"銀","KI":"金",
            "KA":"角","HI":"飛","OU":"王",
            "+FU":"と","+KY":"杏","+KE":"圭","+GI":"全",
            "+KA":"馬","+HI":"龍",
        },
        "g": {
            "FU":"歩","KY":"香","KE":"桂","GI":"銀","KI":"金",
            "KA":"角","HI":"飛","OU":"王",
            "+FU":"と","+KY":"杏","+KE":"圭","+GI":"全",
            "+KA":"馬","+HI":"龍",
        },
    }

    # 成れる駒 -> 成り駒
    PROMOTE_MAP = {
        "FU":"+FU","KY":"+KY","KE":"+KE","GI":"+GI","KA":"+KA","HI":"+HI",
    }
    # 成り駒 -> 元駒
    UNPROMOTE_MAP = {v: k for k, v in PROMOTE_MAP.items()}

    # 金と同じ動き (成り駒に共通)
    _GOLD_DIRS_S = [(-1,0),(-1,-1),(-1,1),(0,-1),(0,1),(1,0)]  # 先手視点
    _GOLD_DIRS_G = [(1,0),(1,-1),(1,1),(0,-1),(0,1),(-1,0)]    # 後手視点

    def __init__(self):
        self.reset()

    def reset(self):
        self.board: list[list] = self._init_board()  # board[row][col] = (color, ptype) or None
        self.turn: str = self.SENTE
        self.hands: dict = {self.SENTE: {}, self.GOTE: {}}  # 持ち駒
        self.move_history: list[str] = []
        self.game_over: bool = False
        self.result: str = ""
        self.last_move: tuple | None = None  # (fr,fc,tr,tc) or (None,None,tr,tc) for drop

    def _init_board(self) -> list[list]:
        b = [[None]*9 for _ in range(9)]
        # 後手陣 (row 0-2): g
        back = ["KY","KE","GI","KI","OU","KI","GI","KE","KY"]
        for c, p in enumerate(back):
            b[0][c] = (self.GOTE, p)
        # 画面は disp_c=8-c で左右反転: col=7→画面左2番目, col=1→画面右2番目
        b[1][7] = (self.GOTE, "HI")   # 後手飛車: 画面左から2番目(8筋側)
        b[1][1] = (self.GOTE, "KA")   # 後手角:   画面右から2番目(2筋側)
        for c in range(9):
            b[2][c] = (self.GOTE, "FU")
        # 先手陣 (row 6-8): s
        for c, p in enumerate(back):
            b[8][c] = (self.SENTE, p)
        b[7][1] = (self.SENTE, "HI")  # 先手飛車: 画面右から2番目(2筋)
        b[7][7] = (self.SENTE, "KA")  # 先手角:   画面左から2番目(8筋)
        for c in range(9):
            b[6][c] = (self.SENTE, "FU")
        return b

    def _enemy(self, color: str) -> str:
        return self.GOTE if color == self.SENTE else self.SENTE

    def _on_board(self, r: int, c: int) -> bool:
        return 0 <= r <= 8 and 0 <= c <= 8

    def _promote_zone(self, color: str, r: int) -> bool:
        return r <= 2 if color == self.SENTE else r >= 6

    def _must_promote(self, color: str, ptype: str, r: int) -> bool:
        """成らないと動けなくなる場合は強制成り"""
        if ptype == "FU" or ptype == "KY":
            return (r == 0 if color == self.SENTE else r == 8)
        if ptype == "KE":
            return (r <= 1 if color == self.SENTE else r >= 7)
        return False

    def _piece_moves_raw(self, color: str, ptype: str, r: int, c: int) -> list[tuple]:
        """(tr, tc) のリスト (盤外・味方駒チェックなし)"""
        s = color == self.SENTE
        dirs_slide = []
        dirs_jump  = []
        one_step   = []

        if ptype == "FU":
            one_step = [(-1,0)] if s else [(1,0)]
        elif ptype == "KY":
            dirs_slide = [(-1,0)] if s else [(1,0)]
        elif ptype == "KE":
            dirs_jump = [(-2,-1),(-2,1)] if s else [(2,-1),(2,1)]
        elif ptype == "GI":
            one_step = [(-1,-1),(-1,0),(-1,1),(1,-1),(1,1)] if s else \
                       [(1,-1),(1,0),(1,1),(-1,-1),(-1,1)]
        elif ptype == "KI":
            one_step = self._GOLD_DIRS_S if s else self._GOLD_DIRS_G
        elif ptype in ("+FU","+KY","+KE","+GI"):
            one_step = self._GOLD_DIRS_S if s else self._GOLD_DIRS_G
        elif ptype == "KA":
            dirs_slide = [(-1,-1),(-1,1),(1,-1),(1,1)]
        elif ptype == "+KA":
            dirs_slide = [(-1,-1),(-1,1),(1,-1),(1,1)]
            one_step   = [(-1,0),(1,0),(0,-1),(0,1)]
        elif ptype == "HI":
            dirs_slide = [(-1,0),(1,0),(0,-1),(0,1)]
        elif ptype == "+HI":
            dirs_slide = [(-1,0),(1,0),(0,-1),(0,1)]
            one_step   = [(-1,-1),(-1,1),(1,-1),(1,1)]
        elif ptype == "OU":
            one_step = [(-1,-1),(-1,0),(-1,1),(0,-1),(0,1),(1,-1),(1,0),(1,1)]

        moves = []
        for dr, dc in one_step:
            moves.append((r+dr, c+dc))
        for dr, dc in dirs_jump:
            moves.append((r+dr, c+dc))
        for dr, dc in dirs_slide:
            nr, nc = r+dr, c+dc
            while self._on_board(nr, nc):
                moves.append((nr, nc))
                if self.board[nr][nc]:
                    break
                nr += dr; nc += dc
        return moves

    def pseudo_legal_moves_sq(self, r: int, c: int) -> list[tuple]:
        """(r,c)の駒の疑似合法手 (tr,tc,promote) リスト"""
        cell = self.board[r][c]
        if not cell: return []
        color, ptype = cell
        moves = []
        for tr, tc in self._piece_moves_raw(color, ptype, r, c):
            if not self._on_board(tr, tc): continue
            target = self.board[tr][tc]
            if target and target[0] == color: continue  # 味方駒
            can_promote = ptype in self.PROMOTE_MAP
            in_zone_from = self._promote_zone(color, r)
            in_zone_to   = self._promote_zone(color, tr)
            must = can_promote and self._must_promote(color, ptype, tr)
            if must:
                moves.append((tr, tc, True))
            elif can_promote and (in_zone_from or in_zone_to):
                moves.append((tr, tc, True))   # 成り
                moves.append((tr, tc, False))  # 不成
            else:
                moves.append((tr, tc, False))
        return moves

    def _find_king(self, color: str) -> tuple | None:
        for r in range(9):
            for c in range(9):
                cell = self.board[r][c]
                if cell and cell[0] == color and cell[1] == "OU":
                    return (r, c)
        return None

    def in_check(self, color: str) -> bool:
        kpos = self._find_king(color)
        if kpos is None: return True
        kr, kc = kpos
        enemy = self._enemy(color)
        for r in range(9):
            for c in range(9):
                cell = self.board[r][c]
                if not cell or cell[0] != enemy: continue
                _, ptype = cell
                for tr, tc in self._piece_moves_raw(enemy, ptype, r, c):
                    if (tr, tc) == (kr, kc): return True
        return False

    def _apply_temp(self, fr, fc, tr, tc, promote: bool, drop_ptype: str | None = None) -> dict:
        """一時適用 (合法性チェックなし)、saved辞書を返す"""
        saved = {
            "board_cell_fr": (fr, fc, self.board[fr][fc]) if fr is not None else None,
            "board_cell_tr": (tr, tc, self.board[tr][tc]),
            "hands": {self.SENTE: dict(self.hands[self.SENTE]),
                      self.GOTE:  dict(self.hands[self.GOTE])},
        }
        if drop_ptype:
            # 打ち駒
            self.board[tr][tc] = (self.turn, drop_ptype)
            h = self.hands[self.turn]
            h[drop_ptype] = h.get(drop_ptype, 0) - 1
            if h[drop_ptype] <= 0: del h[drop_ptype]
        else:
            color, ptype = self.board[fr][fc]
            target = self.board[tr][tc]
            if target:
                cap = self.UNPROMOTE_MAP.get(target[1], target[1])
                self.hands[color][cap] = self.hands[color].get(cap, 0) + 1
            new_ptype = self.PROMOTE_MAP.get(ptype, ptype) if promote else ptype
            self.board[fr][fc] = None
            self.board[tr][tc] = (color, new_ptype)
        return saved

    def _undo_temp(self, saved: dict):
        if saved["board_cell_fr"] is not None:
            r, c, val = saved["board_cell_fr"]
            self.board[r][c] = val
        r, c, val = saved["board_cell_tr"]
        self.board[r][c] = val
        self.hands[self.SENTE] = saved["hands"][self.SENTE]
        self.hands[self.GOTE]  = saved["hands"][self.GOTE]

    def legal_moves(self, color: str) -> list[tuple]:
        """(fr, fc, tr, tc, promote, drop_ptype) のリスト"""
        moves = []
        # 駒の移動
        for r in range(9):
            for c in range(9):
                cell = self.board[r][c]
                if not cell or cell[0] != color: continue
                for tr, tc, promote in self.pseudo_legal_moves_sq(r, c):
                    saved = self._apply_temp(r, c, tr, tc, promote)
                    if not self.in_check(color):
                        moves.append((r, c, tr, tc, promote, None))
                    self._undo_temp(saved)
        # 打ち駒
        for ptype, cnt in list(self.hands[color].items()):  # list()でコピー: イテレート中のサイズ変更を防ぐ
            if cnt <= 0: continue
            for tr in range(9):
                for tc in range(9):
                    if self.board[tr][tc]: continue
                    # 二歩チェック
                    if ptype == "FU":
                        col_has_fu = any(
                            self.board[rr][tc] and self.board[rr][tc][0] == color
                            and self.board[rr][tc][1] == "FU"
                            for rr in range(9)
                        )
                        if col_has_fu: continue
                        # 打ち歩詰めチェック
                        if self._is_uchifuzume(color, tr, tc): continue
                    # 行き所のない駒チェック
                    if ptype == "FU" or ptype == "KY":
                        if color == self.SENTE and tr == 0: continue
                        if color == self.GOTE  and tr == 8: continue
                    if ptype == "KE":
                        if color == self.SENTE and tr <= 1: continue
                        if color == self.GOTE  and tr >= 7: continue
                    saved = self._apply_temp(None, None, tr, tc, False, ptype)
                    if not self.in_check(color):
                        moves.append((None, None, tr, tc, False, ptype))
                    self._undo_temp(saved)
        return moves

    def _is_uchifuzume(self, color: str, tr: int, tc: int) -> bool:
        """打ち歩詰めになるか"""
        saved = self._apply_temp(None, None, tr, tc, False, "FU")
        enemy = self._enemy(color)
        enemy_legal = self.legal_moves(enemy)
        is_zume = (not enemy_legal) and self.in_check(enemy)
        self._undo_temp(saved)
        return is_zume

    def move(self, fr, fc, tr, tc, promote: bool = False, drop_ptype: str | None = None) -> tuple[bool, str]:
        """手を実行。(True, 棋譜) or (False, エラー)"""
        if self.game_over:
            return False, "ゲームは終了しています"
        legal = self.legal_moves(self.turn)
        if (fr, fc, tr, tc, promote, drop_ptype) not in legal:
            return False, "その手は合法ではありません"

        # 実行
        if drop_ptype:
            self.board[tr][tc] = (self.turn, drop_ptype)
            h = self.hands[self.turn]
            h[drop_ptype] = h.get(drop_ptype, 0) - 1
            if h[drop_ptype] <= 0: del h[drop_ptype]
            notation = f"{'☗' if self.turn==self.SENTE else '☖'}{9-tc}{tr+1}{self.PIECE_NAMES_JA.get(drop_ptype,'?')}打"
        else:
            color, ptype = self.board[fr][fc]
            target = self.board[tr][tc]
            if target:
                cap = self.UNPROMOTE_MAP.get(target[1], target[1])
                self.hands[color][cap] = self.hands[color].get(cap, 0) + 1
            new_ptype = self.PROMOTE_MAP.get(ptype, ptype) if promote else ptype
            self.board[fr][fc] = None
            self.board[tr][tc] = (color, new_ptype)
            pro_str = "成" if promote else ""
            notation = f"{'☗' if color==self.SENTE else '☖'}{9-tc}{tr+1}{self.PIECE_NAMES_JA.get(new_ptype,'?')}{pro_str}"

        self.last_move = (fr, fc, tr, tc)
        self.move_history.append(notation)
        self.turn = self._enemy(self.turn)

        # 詰み・ステールメイト確認
        next_legal = self.legal_moves(self.turn)
        if not next_legal:
            winner_name = "先手" if self.turn == self.GOTE else "後手"
            self.game_over = True
            self.result = f"詰み！{winner_name}の勝利"

        return True, notation

    def board_str(self) -> str:
        lines = []
        lines.append("  ９ ８ ７ ６ ５ ４ ３ ２ １")
        lines.append(" +" + "--+"*9)
        for r in range(9):
            row_label = str(r+1)
            cells = []
            for c in range(8, -1, -1):
                cell = self.board[r][c]
                if cell is None:
                    cells.append(" ・")
                else:
                    color, ptype = cell
                    sym = self.PIECE_SYMBOLS[color].get(ptype, "?")
                    if color == self.GOTE:
                        cells.append(f"v{sym}")
                    else:
                        cells.append(f" {sym}")
            lines.append(f"{row_label}|{'|'.join(cells)}|")
            lines.append(" +" + "--+"*9)
        return "\n".join(lines)

    def hand_str(self, color: str) -> str:
        h = self.hands[color]
        if not h: return "なし"
        parts = []
        order = ["HI","KA","KI","GI","KE","KY","FU"]
        for p in order:
            if h.get(p, 0) > 0:
                parts.append(f"{self.PIECE_NAMES_JA.get(p,'?')}×{h[p]}")
        return " ".join(parts) if parts else "なし"


class ShogiAI:
    """将棋AI。4段階難易度。"""

    PIECE_VALUE = {
        "FU":100,"KY":200,"KE":250,"GI":350,"KI":450,
        "KA":600,"HI":700,"OU":10000,
        "+FU":300,"+KY":350,"+KE":350,"+GI":450,
        "+KA":800,"+HI":900,
    }

    DIFFICULTY_SETTINGS = {
        "easy":      {"depth": 0, "random_rate": 1.0},
        "middle":    {"depth": 1, "random_rate": 0.25},
        "hard":      {"depth": 2, "random_rate": 0.0},
        "very_hard": {"depth": 3, "random_rate": 0.0},
    }

    def __init__(self, difficulty: str = "middle", color: str = "g"):
        self.difficulty = difficulty
        self.color = color
        s = self.DIFFICULTY_SETTINGS.get(difficulty, self.DIFFICULTY_SETTINGS["middle"])
        self.depth = s["depth"]
        self.random_rate = s["random_rate"]

    def evaluate(self, g: "ShogiEngine") -> int:
        score = 0
        for r in range(9):
            for c in range(9):
                cell = g.board[r][c]
                if not cell: continue
                color, ptype = cell
                val = self.PIECE_VALUE.get(ptype, 0)
                score += val if color == ShogiEngine.SENTE else -val
        for ptype, cnt in g.hands[ShogiEngine.SENTE].items():
            score += self.PIECE_VALUE.get(ptype, 0) * cnt * 0.8
        for ptype, cnt in g.hands[ShogiEngine.GOTE].items():
            score -= self.PIECE_VALUE.get(ptype, 0) * cnt * 0.8
        return int(score)

    def _minimax(self, g: "ShogiEngine", depth: int, alpha: int, beta: int, maximizing: bool) -> int:
        if depth == 0 or g.game_over:
            return self.evaluate(g)
        color = ShogiEngine.SENTE if maximizing else ShogiEngine.GOTE
        moves = g.legal_moves(color)
        if not moves:
            return self.evaluate(g)
        if maximizing:
            best = -10**9
            for mv in moves:
                fr, fc, tr, tc, promote, drop = mv
                saved = g._apply_temp(fr, fc, tr, tc, promote, drop)
                prev = g.turn; g.turn = ShogiEngine.GOTE
                val = self._minimax(g, depth-1, alpha, beta, False)
                g.turn = prev; g._undo_temp(saved)
                best = max(best, val); alpha = max(alpha, val)
                if beta <= alpha: break
            return best
        else:
            best = 10**9
            for mv in moves:
                fr, fc, tr, tc, promote, drop = mv
                saved = g._apply_temp(fr, fc, tr, tc, promote, drop)
                prev = g.turn; g.turn = ShogiEngine.SENTE
                val = self._minimax(g, depth-1, alpha, beta, True)
                g.turn = prev; g._undo_temp(saved)
                best = min(best, val); beta = min(beta, val)
                if beta <= alpha: break
            return best

    def choose_move(self, g: "ShogiEngine") -> tuple | None:
        moves = g.legal_moves(self.color)
        if not moves: return None
        if self.difficulty == "easy" or (self.random_rate > 0 and random.random() < self.random_rate):
            return random.choice(moves)
        maximizing = (self.color == ShogiEngine.SENTE)
        best_val = -10**9 if maximizing else 10**9
        best_moves = []
        for mv in moves:
            fr, fc, tr, tc, promote, drop = mv
            saved = g._apply_temp(fr, fc, tr, tc, promote, drop)
            prev = g.turn
            g.turn = ShogiEngine.GOTE if self.color == ShogiEngine.SENTE else ShogiEngine.SENTE
            val = self._minimax(g, self.depth-1, -10**9, 10**9, not maximizing)
            g.turn = prev; g._undo_temp(saved)
            if maximizing:
                if val > best_val: best_val = val; best_moves = [mv]
                elif val == best_val: best_moves.append(mv)
            else:
                if val < best_val: best_val = val; best_moves = [mv]
                elif val == best_val: best_moves.append(mv)
        return random.choice(best_moves) if best_moves else random.choice(moves)


# ===== ゲームコメンタータ (将棋・チェス共通) =====
class GameCommentator:
    """
    ゲーム中にペルソナがリアルタイムでテロップ（字幕）を生成する。
    別スレッドでLLMを呼び出し、メインのcursesループをブロックしない。
    """
    MAX_SCROLL = 6   # テロップ保持最大件数
    EXPIRE_SECS = 18 # 1件あたりの表示秒数

    def __init__(self, persona: dict, game_kind: str = "将棋"):
        self.persona   = persona
        self.game_kind = game_kind           # "将棋" or "チェス"
        self._lock     = threading.Lock()
        self._lines: list[tuple[str, float]] = []  # (テキスト, 追加時刻)
        self._busy     = threading.Event()   # スレッドセーフなbusy フラグ

    # ── 公開API ─────────────────────────────────────────────────
    def trigger(self, event: str, context: str = "") -> None:
        """イベントをトリガー。非同期でコメントを生成する。"""
        if self._busy.is_set():
            return  # 前のコメント生成中はスキップ
        self._busy.set()
        threading.Thread(
            target=self._generate,
            args=(event, context),
            daemon=True
        ).start()

    def get_lines(self) -> list[str]:
        """期限切れを除去して現在のテロップ行リストを返す。"""
        now = time.time()
        with self._lock:
            self._lines = [(t, ts) for t, ts in self._lines
                           if now - ts < self.EXPIRE_SECS]
            return [t for t, _ in self._lines[-self.MAX_SCROLL:]]

    def clear(self) -> None:
        with self._lock:
            self._lines.clear()

    # ── 内部 ────────────────────────────────────────────────────
    def _generate(self, event: str, context: str) -> None:
        # _busy はtrigger側でset済み
        try:
            o = _get_ollama()
            if o is None:
                return
            p = self.persona
            fp   = p.get("first_person", "私")
            name = p.get("name", "AI")
            style = p.get("style", "")
            # ペルソナ種別で二人称を決定
            AUTHORITATIVE = {
                "ソクラテス","プラトン","アリストテレス","エピクテトス",
                "マルクス・アウレリウス","トマス・アクィナス","デカルト","スピノザ",
                "ライプニッツ","ロック","ヒューム","カント","ヘーゲル",
                "ショーペンハウアー","ミル","ニーチェ","ウィリアム・ジェームズ",
                "フッサール","ハイデガー","サルトル","ボーヴォワール","ラッセル",
                "前期ウィトゲンシュタイン","後期ウィトゲンシュタイン",
            }
            second_person = "君" if name in AUTHORITATIVE else "先輩"

            sys_content = (
                f"あなたは{name}。口調: {style}。一人称: {fp}。\n"
                f"今、{self.game_kind}の対局を観戦している。ユーザーを『{second_person}』と呼ぶ。\n"
                f"観戦コメントを【1文・30字以内】で述べよ。\n"
                f"説明・解説は不要。キャラとして自然な一言のみ。箇条書き禁止。"
            )
            user_content = (
                f"【イベント】{event}\n"
                f"【状況】{context}\n"
                f"このイベントへの一言コメント（30字以内・1文）を{name}の口調で述べよ。"
            )
            msgs = [
                {"role": "system", "content": sys_content},
                {"role": "user",   "content": user_content},
            ]
            opts = {"temperature": 0.82, "num_predict": 60, "num_ctx": 256}
            result = ""
            deadline = time.time() + 8.0   # 8秒でタイムアウト
            try:
                stream = o.chat(model=MODEL_NAME, messages=msgs,
                                stream=True, options=opts)
                for chunk in stream:
                    if time.time() > deadline:
                        break
                    delta = chunk.get("message", {}).get("content", "")
                    result += delta
                    if len(result) > 60:
                        break
            except Exception:
                return
            # 改行・空行を除去して1行に
            result = result.strip().replace("\n", "　")
            if not result:
                return
            # 30字に切る
            if len(result) > 45:
                result = result[:45].rstrip("、，") + "…"
            with self._lock:
                self._lines.append((f"【{name}】{result}", time.time()))
                if len(self._lines) > self.MAX_SCROLL:
                    self._lines.pop(0)
        finally:
            self._busy.clear()


# ===== 将棋 curses UI =====
_SQ  = 4   # マス幅 (chars)
_SH  = 3   # マス高 (lines)
_SBX = 4   # 盤面左端
_SBY = 3   # 盤面上端 (端末が小さい場合は動的に縮小)
_SI_X = _SBX + _SQ * 9 + 2  # 右パネル開始

_SCP_LIGHT    = 21
_SCP_DARK     = 22
_SCP_SEL      = 23
_SCP_LEGAL    = 24
_SCP_LAST     = 25
_SCP_CHECK    = 26
_SCP_TITLE    = 27
_SCP_PANEL    = 28
_SCP_BTN      = 29
_SCP_STATUS_OK= 30
_SCP_STATUS_WN= 31
_SCP_DROP_HL  = 32
_SCP_COMMENT  = 33  # テロップ（ペルソナコメント）

def _shogi_init_colors():
    curses.start_color()
    curses.use_default_colors()
    # 盤面: 薄茶(YELLOW)/白 → 駒が黒で見やすいコントラスト
    curses.init_pair(_SCP_LIGHT,     curses.COLOR_BLACK,  curses.COLOR_YELLOW)   # 奇数マス: 薄黄
    curses.init_pair(_SCP_DARK,      curses.COLOR_BLACK,  curses.COLOR_WHITE)    # 偶数マス: 白
    curses.init_pair(_SCP_SEL,       curses.COLOR_WHITE,  curses.COLOR_MAGENTA)  # 選択中
    curses.init_pair(_SCP_LEGAL,     curses.COLOR_BLACK,  curses.COLOR_GREEN)    # 移動候補(緑=見やすい)
    curses.init_pair(_SCP_LAST,      curses.COLOR_BLACK,  curses.COLOR_CYAN)     # 直前の手(シアン)
    curses.init_pair(_SCP_CHECK,     curses.COLOR_WHITE,  curses.COLOR_RED)      # 王手
    curses.init_pair(_SCP_TITLE,     curses.COLOR_WHITE,  curses.COLOR_BLUE)     # タイトル(青背景)
    curses.init_pair(_SCP_PANEL,     curses.COLOR_CYAN,   -1)                    # 棋譜パネル(シアン)
    curses.init_pair(_SCP_BTN,       curses.COLOR_BLACK,  curses.COLOR_WHITE)    # ボタン
    curses.init_pair(_SCP_STATUS_OK, curses.COLOR_BLACK,  curses.COLOR_GREEN)    # ステータスOK
    curses.init_pair(_SCP_STATUS_WN, curses.COLOR_WHITE,  curses.COLOR_RED)      # 警告
    curses.init_pair(_SCP_DROP_HL,   curses.COLOR_BLACK,  curses.COLOR_YELLOW)   # 持駒選択ハイライト
    curses.init_pair(_SCP_COMMENT,   curses.COLOR_BLACK,  curses.COLOR_MAGENTA)  # ペルソナテロップ


def _shogi_curses_main(stdscr, g: "ShogiEngine", ai: "ShogiAI | None" = None,
                       commentator: "GameCommentator | None" = None):
    """将棋 cursesメインループ"""
    _shogi_init_colors()
    curses.curs_set(0)
    curses.mousemask(curses.ALL_MOUSE_EVENTS | curses.REPORT_MOUSE_POSITION)
    curses.mouseinterval(0)
    stdscr.keypad(True)
    stdscr.timeout(80)

    # ── 端末サイズに合わせてレイアウトを動的調整 ──────────────────
    global _SBY, _SH, _SI_X
    term_h, term_w = stdscr.getmaxyx()
    # _SH=3 の場合、必要行数 = 3+2+27+3+2 = 37行
    # 端末が小さければ _SH=2 (=3+2+18+3+2=28行) に切り替え
    if term_h < 37:
        _SH = 2
    else:
        _SH = 3
    # SBYを確保。収まらなければ2に縮小
    _SBY = 3
    if _SBY + 9 * _SH + 5 > term_h:
        _SBY = 2
    _SI_X = _SBX + _SQ * 9 + 2
    # ──────────────────────────────────────────────────────────────
    selected: tuple | None = None      # 選択中マス (r, c) or ("hand", color, ptype)
    legal_moves_cache: list = []       # 合法手キャッシュ
    status_msg  = ""
    status_warn = False
    undo_stack: list = []
    _diff_labels = {"easy":"Easy","middle":"Middle","hard":"Hard","very_hard":"Very Hard"}

    if ai:
        status_msg = f"将棋 AI対戦[{_diff_labels.get(ai.difficulty,'')}] — 先手(あなた)から！"
    else:
        status_msg = "将棋: クリックして駒を選択"

    BUTTONS = [("  新局  ","new"),("  待った ","undo"),("  終了  ","quit")]

    def _snapshot():
        import copy
        return {
            "board": [row[:] for row in g.board],
            "turn": g.turn,
            "hands": {ShogiEngine.SENTE: dict(g.hands[ShogiEngine.SENTE]),
                      ShogiEngine.GOTE:  dict(g.hands[ShogiEngine.GOTE])},
            "move_history": g.move_history[:],
            "game_over": g.game_over,
            "result": g.result,
            "last_move": g.last_move,
        }

    def _restore(snap):
        g.board        = snap["board"]
        g.turn         = snap["turn"]
        g.hands        = snap["hands"]
        g.move_history = snap["move_history"]
        g.game_over    = snap["game_over"]
        g.result       = snap["result"]
        g.last_move    = snap["last_move"]

    def _sq_to_screen(r, c):
        # 将棋盤は右から左に列が増える (9列目=左)
        # 画面上: c=0(9筋)=左端, c=8(1筋)=右端
        disp_c = 8 - c  # 盤面左端からのオフセット
        return (_SBY + r * _SH, _SBX + disp_c * _SQ)

    def _screen_to_sq(my, mx):
        r = (my - _SBY) // _SH
        dc = (mx - _SBX) // _SQ
        c  = 8 - dc
        if 0 <= r <= 8 and 0 <= c <= 8:
            ry = my - (_SBY + r * _SH)
            rx = mx - (_SBX + dc * _SQ)
            if 0 <= ry < _SH and 0 <= rx < _SQ:
                return (r, c)
        return None

    def _draw_board():
        last = g.last_move
        last_sqs = set()
        if last:
            fr, fc, tr, tc = last
            if fr is not None: last_sqs.add((fr, fc))
            last_sqs.add((tr, tc))

        legal_tgts = set()
        if isinstance(selected, tuple) and len(selected) == 2:
            for mv in legal_moves_cache:
                _, _, tr, tc, _, _ = mv
                if mv[0] == selected[0] and mv[1] == selected[1]:
                    legal_tgts.add((tr, tc))
        elif isinstance(selected, tuple) and len(selected) == 3 and selected[0] == "hand":
            for mv in legal_moves_cache:
                _, _, tr, tc, _, drop = mv
                if drop == selected[2]:
                    legal_tgts.add((tr, tc))

        king_r, king_c = None, None
        kpos = g._find_king(g.turn)
        in_chk = g.in_check(g.turn)
        if kpos: king_r, king_c = kpos

        for r in range(9):
            for c in range(9):
                sy, sx = _sq_to_screen(r, c)
                cell = g.board[r][c]
                if cell:
                    color, ptype = cell
                    sym = ShogiEngine.PIECE_SYMBOLS[color].get(ptype, "?")
                    is_gote = (color == ShogiEngine.GOTE)
                    # 後手駒: 上段に駒文字を置いて「逆向き」に見せる
                    # 先手駒: 下段に駒文字を置く（_SH=2時は中段と同じ）
                    mid_text = f" {sym} "[:_SQ].ljust(_SQ)  # 駒文字（センタリング）
                    blank    = " " * _SQ
                else:
                    is_gote  = False
                    mid_text = " ・ "[:_SQ].ljust(_SQ)
                    blank    = " " * _SQ

                if in_chk and (r, c) == (king_r, king_c):
                    cp = _SCP_CHECK
                elif isinstance(selected, tuple) and len(selected)==2 and selected == (r, c):
                    cp = _SCP_SEL
                elif (r, c) in legal_tgts:
                    cp = _SCP_LEGAL
                elif (r, c) in last_sqs:
                    cp = _SCP_LAST
                else:
                    cp = _SCP_LIGHT if (r + c) % 2 == 0 else _SCP_DARK

                attr     = curses.color_pair(cp)
                attr_b   = curses.color_pair(cp) | curses.A_BOLD
                attr_dim = curses.color_pair(cp) | curses.A_DIM

                try:
                    if _SH >= 3:
                        if cell:
                            if is_gote:
                                # 後手: 上段=駒文字(BOLD・暗め)、中段・下段=空白
                                stdscr.addstr(sy,   sx, mid_text, attr_dim)
                                stdscr.addstr(sy+1, sx, blank,    attr)
                                stdscr.addstr(sy+2, sx, blank,    attr)
                            else:
                                # 先手: 上段=空白、中段=空白、下段=駒文字(BOLD)
                                stdscr.addstr(sy,   sx, blank,    attr)
                                stdscr.addstr(sy+1, sx, blank,    attr)
                                stdscr.addstr(sy+2, sx, mid_text, attr_b)
                        else:
                            # 空マス: 中段にドット
                            stdscr.addstr(sy,   sx, blank,    attr)
                            stdscr.addstr(sy+1, sx, mid_text, attr)
                            stdscr.addstr(sy+2, sx, blank,    attr)
                    else:
                        # _SH=2: 後手=上段、先手=下段
                        if cell:
                            if is_gote:
                                stdscr.addstr(sy,   sx, mid_text, attr_dim)
                                stdscr.addstr(sy+1, sx, blank,    attr)
                            else:
                                stdscr.addstr(sy,   sx, blank,    attr)
                                stdscr.addstr(sy+1, sx, mid_text, attr_b)
                        else:
                            stdscr.addstr(sy,   sx, mid_text, attr)
                            stdscr.addstr(sy+1, sx, blank,    attr)
                except curses.error:
                    pass

        # 列ラベル (9〜1)
        for c in range(9):
            sy_lbl, sx_lbl = _sq_to_screen(0, c)
            try:
                stdscr.addstr(_SBY - 1, sx_lbl, str(9 - c), curses.color_pair(_SCP_PANEL) | curses.A_BOLD)
            except curses.error:
                pass
        # 行ラベル (一〜九)
        kanji_row = "一二三四五六七八九"
        for r in range(9):
            sy_lbl = _SBY + r * _SH + (_SH // 2)
            try:
                stdscr.addstr(sy_lbl, _SBX - 2, kanji_row[r], curses.color_pair(_SCP_PANEL) | curses.A_BOLD)
            except curses.error:
                pass

    def _draw_hands():
        """後手持ち駒(上部)・先手持ち駒(下部)を描画"""
        h, w_max = stdscr.getmaxyx()

        # 後手持ち駒 (上)
        gote_hand = g.hand_str(ShogiEngine.GOTE)
        try:
            stdscr.addstr(1, _SBX, f"後手持駒: {gote_hand}".ljust(40), curses.color_pair(_SCP_PANEL))
        except curses.error:
            pass

        # 先手持ち駒 (下)
        sente_hand = g.hand_str(ShogiEngine.SENTE)
        try:
            stdscr.addstr(_SBY + 9*_SH + 1, _SBX, f"先手持駒: {sente_hand}".ljust(40), curses.color_pair(_SCP_PANEL))
        except curses.error:
            pass

        # 持ち駒クリック領域を描画 (先手のみ / プレイヤーターン時)
        if g.turn == ShogiEngine.SENTE and (ai is None or ai.color != ShogiEngine.SENTE):
            hand = g.hands[ShogiEngine.SENTE]
            order = ["HI","KA","KI","GI","KE","KY","FU"]
            x_off = _SBX
            y_row = _SBY + 9*_SH + 2
            for pt in order:
                if hand.get(pt, 0) > 0:
                    sym = ShogiEngine.PIECE_NAMES_JA.get(pt, "?")
                    is_sel = isinstance(selected, tuple) and len(selected)==3 and selected[2]==pt
                    cp = _SCP_DROP_HL if is_sel else _SCP_BTN
                    try:
                        stdscr.addstr(y_row, x_off, f"[{sym}]", curses.color_pair(cp) | curses.A_BOLD)
                    except curses.error:
                        pass
                    x_off += 5

    def _hand_click_at(my, mx) -> str | None:
        """先手持ち駒クリックで駒種を返す"""
        y_row = _SBY + 9*_SH + 2
        if my != y_row: return None
        hand = g.hands[ShogiEngine.SENTE]
        order = ["HI","KA","KI","GI","KE","KY","FU"]
        x_off = _SBX
        for pt in order:
            if hand.get(pt, 0) > 0:
                if x_off <= mx < x_off + 4:
                    return pt
                x_off += 5
        return None

    def _draw_panel():
        px = _SI_X
        h, _ = stdscr.getmaxyx()

        # 棋譜
        hist = g.move_history
        try:
            stdscr.addstr(_SBY, px, "── 棋譜 ──────────", curses.color_pair(_SCP_PANEL)|curses.A_DIM)
        except curses.error:
            pass
        panel_h = max(4, h - _SBY - 6)
        start_i = max(0, len(hist) - panel_h)
        for i, notation in enumerate(hist[start_i:]):
            try:
                stdscr.addstr(_SBY + 1 + i, px, f"{start_i+i+1:3d}. {notation[:20]}", curses.color_pair(_SCP_PANEL))
            except curses.error:
                pass

        # ボタン
        btn_y = h - 4
        for i, (label, _) in enumerate(BUTTONS):
            try:
                stdscr.addstr(btn_y, px + i*10, label, curses.color_pair(_SCP_BTN)|curses.A_BOLD)
            except curses.error:
                pass

    def _btn_at(my, mx):
        h, _ = stdscr.getmaxyx()
        btn_y = h - 4
        px = _SI_X
        for i, (label, action) in enumerate(BUTTONS):
            lx = px + i*10
            if my == btn_y and lx <= mx < lx + len(label):
                return action
        return None

    def _draw_title():
        turn_str = "☗先手" if g.turn == ShogiEngine.SENTE else "☖後手"
        chk_str = " 【王手！】" if g.in_check(g.turn) else ""
        ai_str = f"  [AI:{_diff_labels.get(ai.difficulty,'')}]" if ai else ""
        move_n = len(g.move_history)
        title = f"  将棋{ai_str}  {turn_str}の番{chk_str}   {move_n}手目  "
        try:
            stdscr.addstr(0, 0, title.ljust(80), curses.color_pair(_SCP_TITLE)|curses.A_BOLD)
        except curses.error:
            pass

    def _draw_status(msg, warn=False):
        h, w_max = stdscr.getmaxyx()
        cp = _SCP_STATUS_WN if warn else _SCP_STATUS_OK
        try:
            stdscr.addstr(h-2, 0, f"  {msg}  ".ljust(w_max-1), curses.color_pair(cp))
        except curses.error:
            pass

    def _draw_telop():
        """ペルソナのテロップを最下行に表示"""
        if commentator is None:
            return
        h, w_max = stdscr.getmaxyx()
        lines = commentator.get_lines()
        if not lines:
            return
        # 最新の1行だけ最下行に表示
        text = lines[-1]
        try:
            stdscr.addstr(h-1, 0, f" ♟ {text} ".ljust(w_max-1),
                          curses.color_pair(_SCP_COMMENT) | curses.A_BOLD)
        except curses.error:
            pass

    def _redraw():
        stdscr.erase()
        _draw_title()
        _draw_board()
        _draw_hands()
        _draw_panel()
        _draw_status(status_msg, status_warn)
        _draw_telop()
        stdscr.refresh()

    def _refresh_legal(sel):
        nonlocal legal_moves_cache
        color = g.turn
        all_legal = g.legal_moves(color)
        if sel is None:
            legal_moves_cache = all_legal
            return
        if isinstance(sel, tuple) and len(sel) == 2:
            r, c = sel
            legal_moves_cache = [mv for mv in all_legal if mv[0]==r and mv[1]==c]
        elif isinstance(sel, tuple) and len(sel) == 3:
            _, _, pt = sel
            legal_moves_cache = [mv for mv in all_legal if mv[5]==pt]
        else:
            legal_moves_cache = all_legal

    def _do_move(mv):
        nonlocal selected, legal_moves_cache, status_msg, status_warn
        snap = _snapshot()
        fr, fc, tr, tc, promote, drop = mv
        # 着手前の取られる駒を記録（コメント判定用・軽量）
        captured = g.board[tr][tc]
        ok, msg = g.move(fr, fc, tr, tc, promote, drop)
        if ok:
            undo_stack.append(snap)
            if len(undo_stack) > 80: undo_stack.pop(0)
            selected = None
            legal_moves_cache = []
            status_msg = f"✔ {msg}"
            status_warn = False
            # ── コメンタートリガー ──────────────────────────
            if commentator:
                in_chk = g.in_check(g.turn)
                pname  = ShogiEngine.PIECE_NAMES_JA.get(
                    (drop or (g.board[tr][tc][1] if g.board[tr][tc] else "")), "")
                # 取った駒の価値で「大きな駒得」を判定（評価関数を呼ばない）
                HIGH_VALUE = {"HI", "KA", "KIN", "GIN", "RYU", "UMA"}
                big_capture = captured and captured[1] in HIGH_VALUE
                if g.game_over:
                    event   = "ゲームセット"
                    context = f"結果: {g.result}"
                elif in_chk:
                    event   = "王手"
                    context = f"{msg} — 王手！ 手数:{len(g.move_history)}"
                elif promote:
                    event   = "駒が成った"
                    context = f"{pname}が成った。{msg}"
                elif drop:
                    event   = "持ち駒を打った"
                    context = f"{pname}を打った。{msg}"
                elif big_capture:
                    event   = "大駒を取った"
                    context = f"{msg}"
                else:
                    if _rnd_game.random() < 0.3:
                        event   = "指し手"
                        context = f"{msg} (手数:{len(g.move_history)})"
                    else:
                        event = ""
                if event:
                    commentator.trigger(event, context)
            # ────────────────────────────────────────────────
            if g.game_over:
                status_msg = f"🏆 {g.result}"
                status_warn = True
        else:
            status_msg = f"✖ {msg}"
            status_warn = True
        return ok

    # ── メインループ ───────────────────────────────────────────
    import random as _rnd_game
    _ai_thread: threading.Thread | None = None   # AI思考スレッド
    _ai_result: list = []                        # [mv] or [] — スレッド間共有

    def _ai_think_bg():
        """バックグラウンドでAIの手を計算。結果を_ai_resultに格納。"""
        try:
            mv = ai.choose_move(g)
            _ai_result.clear()
            if mv:
                _ai_result.append(mv)
        except Exception:
            _ai_result.clear()

    while True:
        # AI手番: バックグラウンドスレッドで思考、完了したら着手
        if ai and not g.game_over and g.turn == ai.color:
            # スレッドが走っていなければ開始
            if _ai_thread is None or not _ai_thread.is_alive():
                if _ai_result:
                    # 思考完了 → 着手
                    mv = _ai_result[0]
                    _ai_result.clear()
                    _ai_thread = None
                    snap = _snapshot()
                    fr, fc, tr, tc, promote, drop = mv
                    ok, msg = g.move(fr, fc, tr, tc, promote, drop)
                    if ok:
                        undo_stack.append(snap)
                        if len(undo_stack) > 80: undo_stack.pop(0)
                        selected = None; legal_moves_cache = []
                        status_msg = f"AI [{_diff_labels.get(ai.difficulty,'')}]: {msg}"
                        status_warn = False
                        if g.game_over:
                            status_msg = f"🏆 {g.result}"; status_warn = True
                        if commentator:
                            in_chk = g.in_check(g.turn)
                            if g.game_over:
                                commentator.trigger("AIが勝利", f"結果: {g.result}")
                            elif in_chk:
                                commentator.trigger("AIが王手", f"AIの手: {msg}")
                            elif _rnd_game.random() < 0.5:
                                commentator.trigger("AIの指し手", f"AI: {msg} (手数:{len(g.move_history)})")
                else:
                    # 思考スレッドを起動
                    _ai_result.clear()
                    status_msg = f"AI [{_diff_labels.get(ai.difficulty,'')}] 思考中..."
                    status_warn = False
                    _ai_thread = threading.Thread(target=_ai_think_bg, daemon=True)
                    _ai_thread.start()
            _redraw()
            stdscr.timeout(80)
            stdscr.getch()   # イベントを消化してCPUを解放（フリーズ防止）
            continue

        _redraw()
        key = stdscr.getch()

        if key == curses.KEY_MOUSE:
            try:
                _, mx, my, _, bstate = curses.getmouse()
            except curses.error:
                continue
            if not (bstate & curses.BUTTON1_CLICKED or bstate & curses.BUTTON1_PRESSED):
                continue

            # ボタン
            action = _btn_at(my, mx)
            if action == "quit":
                return "将棋終了"
            if action == "new":
                g.reset()
                undo_stack.clear()
                selected = None; legal_moves_cache = []
                ai_str = f"[AI:{_diff_labels.get(ai.difficulty,'')}] " if ai else ""
                status_msg = f"新しい対局を開始しました {ai_str}"; status_warn = False
                continue
            if action == "undo":
                # AIモードの場合は2手戻す
                steps = 2 if ai and len(undo_stack) >= 2 else 1
                for _ in range(steps):
                    if undo_stack:
                        _restore(undo_stack.pop())
                selected = None; legal_moves_cache = []
                status_msg = "待った！1手戻しました"; status_warn = False
                continue

            if g.game_over:
                status_msg = f"対局終了: {g.result}  (新局 で新しいゲーム)"; status_warn = True
                continue

            # AIモード: AIの手番には操作不可
            if ai and g.turn == ai.color:
                status_msg = "AIが考えています..."; status_warn = False
                continue

            # 先手持ち駒クリック
            pt = _hand_click_at(my, mx)
            if pt is not None:
                if g.hands[ShogiEngine.SENTE].get(pt, 0) > 0:
                    selected = ("hand", ShogiEngine.SENTE, pt)
                    _refresh_legal(selected)
                    status_msg = f"打ち駒: {ShogiEngine.PIECE_NAMES_JA.get(pt,'?')} — 打つ場所をクリック"
                    status_warn = False
                continue

            # 盤面クリック
            sq = _screen_to_sq(my, mx)
            if sq is None:
                continue
            r, c = sq

            if selected is None:
                # 駒選択
                cell = g.board[r][c]
                if ai and cell and cell[0] == ai.color:
                    status_msg = "それはAIの駒です"; status_warn = True
                elif cell and cell[0] == g.turn:
                    selected = (r, c)
                    _refresh_legal(selected)
                    pname = ShogiEngine.PIECE_NAMES_JA.get(cell[1], cell[1])
                    status_msg = f"選択: {9-c}{'一二三四五六七八九'[r]}({pname}) — 移動先をクリック"
                    status_warn = False
                elif cell:
                    status_msg = f"{'先手' if g.turn==ShogiEngine.SENTE else '後手'}の番です"; status_warn = True
                else:
                    status_msg = "その位置に駒がありません"; status_warn = True

            else:
                # 移動先クリック
                if isinstance(selected, tuple) and len(selected) == 2 and selected == (r, c):
                    selected = None; legal_moves_cache = []
                    status_msg = "選択解除"; status_warn = False
                else:
                    # 合法手の中から候補を探す
                    if isinstance(selected, tuple) and len(selected) == 2:
                        fr2, fc2 = selected
                        cands = [mv for mv in legal_moves_cache if mv[2]==r and mv[3]==c]
                    else:
                        # 打ち駒
                        _, _, drop_pt = selected
                        cands = [mv for mv in legal_moves_cache if mv[2]==r and mv[3]==c and mv[5]==drop_pt]
                        fr2, fc2 = None, None

                    if not cands:
                        # 別の自駒をクリック → 選択し直し
                        cell = g.board[r][c]
                        if cell and cell[0] == g.turn:
                            selected = (r, c)
                            _refresh_legal(selected)
                            pname = ShogiEngine.PIECE_NAMES_JA.get(cell[1], cell[1])
                            status_msg = f"選択変更: {9-c}{'一二三四五六七八九'[r]}({pname})"
                            status_warn = False
                        else:
                            selected = None; legal_moves_cache = []
                            status_msg = "合法手ではありません"; status_warn = True
                    elif len(cands) == 1:
                        _do_move(cands[0])
                    else:
                        # 成り/不成りの選択 (promote=True/False)
                        promote_mv = next((mv for mv in cands if mv[4]), None)
                        nopro_mv   = next((mv for mv in cands if not mv[4]), None)
                        # ポップアップで選択 (簡易: y/n キー待ち)
                        h_s, w_s = stdscr.getmaxyx()
                        py, px_ = h_s//2-2, w_s//2-12
                        cp = curses.color_pair(_SCP_STATUS_WN) | curses.A_BOLD
                        try:
                            stdscr.addstr(py,   px_, "┌─────────────────────────┐", cp)
                            stdscr.addstr(py+1, px_, "│  成りますか？(y=成る/n=不成) │", cp)
                            stdscr.addstr(py+2, px_, "└─────────────────────────┘", cp)
                        except curses.error:
                            pass
                        stdscr.refresh()
                        while True:
                            pk = stdscr.getch()
                            if pk in (ord('y'), ord('Y')) and promote_mv:
                                _do_move(promote_mv); break
                            elif pk in (ord('n'), ord('N')) and nopro_mv:
                                _do_move(nopro_mv); break
                            elif pk in (ord('q'), 27):
                                selected = None; legal_moves_cache = []
                                status_msg = "キャンセル"; status_warn = False; break

        elif key in (ord('q'), ord('Q'), 27):
            return "将棋終了"
        elif key in (ord('n'), ord('N')):
            g.reset(); undo_stack.clear()
            selected = None; legal_moves_cache = []
            status_msg = "新しい対局"; status_warn = False
        elif key in (ord('u'), ord('U')):
            if undo_stack:
                _restore(undo_stack.pop())
                selected = None; legal_moves_cache = []
                status_msg = "待った！"; status_warn = False
            else:
                status_msg = "戻せる手がありません"; status_warn = True


_SHOGI_GAME: "ShogiEngine | None" = None

def handle_shogi(arg: str, persona: dict | None = None) -> str:
    """将棋エントリポイント。/shogi [easy|middle|hard|very_hard]"""
    global _SHOGI_GAME
    arg = arg.strip().lower()

    difficulty_map = {
        "easy": "easy", "イージー": "easy", "簡単": "easy",
        "middle": "middle", "ミドル": "middle", "普通": "middle", "normal": "middle",
        "hard": "hard", "ハード": "hard", "難しい": "hard",
        "very_hard": "very_hard", "veryhard": "very_hard", "最難関": "very_hard",
        "very hard": "very_hard", "超難": "very_hard",
    }
    ai_difficulty = None
    for key, val in difficulty_map.items():
        if key in arg:
            ai_difficulty = val
            break

    if _SHOGI_GAME is None or "new" in arg or ai_difficulty is not None:
        _SHOGI_GAME = ShogiEngine()

    ai = ShogiAI(difficulty=ai_difficulty, color=ShogiEngine.GOTE) if ai_difficulty else None
    # ペルソナコメンタータ生成
    _persona = persona or {"name": "ソクラテス", "style": "問答家口調。語尾「〜かね？」", "first_person": "私"}
    commentator = GameCommentator(_persona, game_kind="将棋")

    try:
        result = curses.wrapper(_shogi_curses_main, _SHOGI_GAME, ai, commentator)
    except Exception as e:
        return f"\033[31m将棋起動エラー: {e}\033[0m"
    return f"\033[32m{result or '将棋を終了しました'}\033[0m"


# ===== 麻雀ゲーム =====
_MAHJONG_HTML_PATH: str | None = None

def handle_mahjong(arg: str) -> str:
    """
    /mj [3|4] [tonpu]  — ブラウザで本格麻雀を起動する。
      3        : 3人麻雀（デフォルト: 東風戦）
      4        : 4人麻雀（デフォルト: 東風戦）
      tonpu    : 東南戦（4人のみ）
    HTMLファイルをテンポラリに書き出してブラウザで開く。
    """
    global _MAHJONG_HTML_PATH
    import tempfile, webbrowser, pathlib

    arg = arg.strip().lower()
    num_players = 3 if "3" in arg else 4
    mode = "tonpu" if "tonpu" in arg else "east"  # east=東風戦, tonpu=東南戦

    # ── HTML生成 ──────────────────────────────────────────────
    html_content = _build_mahjong_html(num_players, mode)

    # ── ファイル確保（同じパスを使い回してタブ増殖を防ぐ）──
    # 注意: パスが存在してもHTMLは必ず上書きする（モード/人数変更に対応）
    if _MAHJONG_HTML_PATH and pathlib.Path(_MAHJONG_HTML_PATH).exists():
        html_path = _MAHJONG_HTML_PATH
    else:
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".html", delete=False,
            encoding="utf-8", prefix="s01_mahjong_"
        )
        html_path = tmp.name
        _MAHJONG_HTML_PATH = html_path
        tmp.close()

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    # ── ブラウザ起動 ──────────────────────────────────────────
    # Brave を優先して起動する（EdgeはローカルHTMLをブロックする場合があるため）。
    # Brave が見つからなければ Chrome → Firefox → webbrowser.open() の順でフォールバック。
    file_uri = pathlib.Path(html_path).as_uri()
    label = f"{num_players}人麻雀({'東南戦' if mode == 'tonpu' else '東風戦'})"

    def _try_open_browser(uri: str) -> tuple[bool, str]:
        """Braveを優先してブラウザを起動。(成功フラグ, 使用ブラウザ名) を返す。"""
        _sys = platform.system()

        # ── Windows ──────────────────────────────────────────
        if _sys == "Windows":
            candidates = [
                # Brave（ユーザーインストール）
                (os.path.expandvars(r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe"), "Brave"),
                # Brave（全ユーザー）
                (os.path.expandvars(r"%PROGRAMFILES%\BraveSoftware\Brave-Browser\Application\brave.exe"), "Brave"),
                (os.path.expandvars(r"%PROGRAMFILES(X86)%\BraveSoftware\Brave-Browser\Application\brave.exe"), "Brave"),
                # Chrome
                (os.path.expandvars(r"%PROGRAMFILES%\Google\Chrome\Application\chrome.exe"), "Chrome"),
                (os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"), "Chrome"),
                # Firefox
                (os.path.expandvars(r"%PROGRAMFILES%\Mozilla Firefox\firefox.exe"), "Firefox"),
            ]
            for exe, name in candidates:
                if os.path.isfile(exe):
                    try:
                        S.Popen([exe, uri])
                        return True, name
                    except Exception:
                        continue

        # ── macOS ─────────────────────────────────────────────
        elif _sys == "Darwin":
            mac_candidates = [
                (["/Applications/Brave Browser.app/Contents/MacOS/Brave Browser", uri], "Brave"),
                (["open", "-a", "Brave Browser", uri], "Brave"),
                (["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", uri], "Chrome"),
                (["open", "-a", "Google Chrome", uri], "Chrome"),
                (["open", "-a", "Firefox", uri], "Firefox"),
            ]
            for cmd, name in mac_candidates:
                try:
                    S.Popen(cmd)
                    return True, name
                except Exception:
                    continue

        # ── Linux ─────────────────────────────────────────────
        else:
            linux_bins = [
                ("brave-browser", "Brave"),
                ("brave", "Brave"),
                ("google-chrome", "Chrome"),
                ("google-chrome-stable", "Chrome"),
                ("chromium-browser", "Chromium"),
                ("chromium", "Chromium"),
                ("firefox", "Firefox"),
            ]
            for bin_name, display_name in linux_bins:
                if shutil.which(bin_name):
                    try:
                        S.Popen([bin_name, uri])
                        return True, display_name
                    except Exception:
                        continue

        # ── 最終フォールバック: webbrowser モジュール ──────────
        try:
            webbrowser.open(uri)
            return True, "デフォルトブラウザ"
        except Exception as e:
            return False, str(e)

    ok, browser_name = _try_open_browser(file_uri)
    if ok:
        return (
            f"\033[32m🀄 {label} を {browser_name} で起動しました\033[0m\n"
            f"\033[90m   ファイル: {html_path}\033[0m\n"
            f"\033[33m   /mj 3      → 3人麻雀\033[0m\n"
            f"\033[33m   /mj 4      → 4人麻雀（東風戦）\033[0m\n"
            f"\033[33m   /mj tonpu  → 4人麻雀（東南戦）\033[0m"
        )
    else:
        return (
            f"\033[33mブラウザ自動起動失敗: {browser_name}\033[0m\n"
            f"次のURLをBraveのアドレスバーに貼り付けてください:\n{file_uri}"
        )


def _build_mahjong_html(num_players: int = 4, mode: str = "east") -> str:
    """麻雀ゲームの完全なHTMLを文字列で返す。"""
    # 起動時に自動で指定モードのゲームを開始するJSを差し込む
    auto_start_js = f"startGame({num_players},'{mode}');"
    # ── HTML本体 ──────────────────────────────────────────────
    return r"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>本格麻雀 — S-01</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#1a1a2e;--bg2:#16213e;--bg3:#0f3460;
  --green:#1b5e20;--green2:#2e7d32;--green3:#388e3c;
  --tile:#f5e6c8;--tile-s:#e8d5a3;--tile-h:#d4a853;
  --red:#e53935;--blue:#1976d2;--gold:#ffd700;--silver:#c0c0c0;
  --text:#f0f0f0;--text2:#b0b0b0;--text3:#707070;
  --radius:6px;--shadow:0 2px 8px rgba(0,0,0,.5);
  --font:'Noto Sans JP',sans-serif;
}
body{background:var(--bg);color:var(--text);font-family:var(--font);min-height:100vh;overflow-x:hidden;user-select:none}
#app{display:flex;flex-direction:column;align-items:center;min-height:100vh}
.screen{display:none;width:100%;max-width:900px;padding:20px}
.screen.active{display:flex;flex-direction:column;align-items:center}
#title-screen{justify-content:center;min-height:100vh;gap:32px}
.title-logo{font-size:64px;font-weight:900;letter-spacing:8px;color:var(--gold);text-shadow:0 0 20px rgba(255,215,0,.4)}
.title-sub{font-size:14px;letter-spacing:4px;color:var(--text2)}
.btn-group{display:flex;flex-direction:column;gap:12px;width:280px}
.btn{padding:14px 32px;border:none;border-radius:var(--radius);font-size:16px;font-weight:700;cursor:pointer;transition:all .15s;letter-spacing:2px}
.btn-primary{background:linear-gradient(135deg,#b8860b,#ffd700);color:#1a1a00}
.btn-primary:hover{filter:brightness(1.15);transform:translateY(-2px)}
.btn-secondary{background:rgba(255,255,255,.08);color:var(--text);border:1px solid rgba(255,255,255,.2)}
.btn-secondary:hover{background:rgba(255,255,255,.15)}
#game-screen{padding:8px;max-width:960px;width:100%}
.table-area{position:relative;background:radial-gradient(ellipse at center,var(--green3) 0%,var(--green2) 50%,var(--green) 100%);border-radius:12px;border:4px solid #5d4037;box-shadow:inset 0 0 40px rgba(0,0,0,.3),var(--shadow);padding:8px;display:grid;grid-template-areas:"top top top" "left center right" "bottom bottom bottom";grid-template-rows:auto 1fr auto;grid-template-columns:auto 1fr auto;gap:4px;min-height:420px}
.seat-top{grid-area:top;display:flex;flex-direction:column;align-items:center;gap:2px}
.seat-left{grid-area:left;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:2px}
.seat-right{grid-area:right;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:2px}
.seat-info{background:rgba(0,0,0,.4);border-radius:4px;padding:3px 8px;font-size:11px;text-align:center;border:1px solid rgba(255,255,255,.1)}
.seat-name{font-weight:700;color:var(--gold)}
.seat-score{color:var(--text2);font-size:10px}
.seat-wind{font-size:10px;color:var(--silver)}
.ai-hand{display:flex;gap:2px}
.tile-back{width:24px;height:34px;background:linear-gradient(135deg,#1565c0,#0d47a1);border-radius:3px;border:1px solid rgba(255,255,255,.3);box-shadow:1px 1px 3px rgba(0,0,0,.5)}
.tile-back.small{width:18px;height:26px}
.seat-left .ai-hand,.seat-right .ai-hand{flex-direction:column}
.seat-left .tile-back,.seat-right .tile-back{width:34px;height:18px}
.center-area{grid-area:center;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:6px}
.info-panel{background:rgba(0,0,0,.5);border-radius:8px;padding:6px 16px;text-align:center;border:1px solid rgba(255,215,0,.3)}
.round-info{font-size:13px;color:var(--gold);font-weight:700}
.dora-area{display:flex;gap:4px;align-items:center}
.dora-label{font-size:10px;color:var(--text2)}
.pond{background:rgba(0,0,0,.2);border-radius:4px;padding:4px;display:flex;flex-wrap:wrap;gap:1px;align-content:flex-start;min-height:60px;max-height:80px;overflow:hidden;border:1px solid rgba(255,255,255,.05)}
.tile{background:var(--tile);color:#1a1a00;border-radius:4px;border:1px solid var(--tile-h);display:inline-flex;align-items:center;justify-content:center;font-size:13px;font-weight:700;cursor:pointer;box-shadow:1px 2px 3px rgba(0,0,0,.4),inset 0 -1px 0 rgba(0,0,0,.2);transition:all .1s;position:relative;flex-shrink:0}
.tile:hover{filter:brightness(1.1);transform:translateY(-2px)}
.tile.selected{transform:translateY(-8px);box-shadow:0 6px 12px rgba(255,215,0,.4),1px 2px 3px rgba(0,0,0,.4);border-color:var(--gold)}
.tile.man{color:#c62828}.tile.pin{color:#1565c0}.tile.sou{color:#2e7d32}.tile.honor{color:#4a148c}
.tile.discarded{width:20px;height:28px;font-size:9px;cursor:default}
.tile.discarded:hover{transform:none;filter:none}
.tile.full{width:36px;height:50px;font-size:18px}
.tile.medium{width:28px;height:40px;font-size:13px}
.tile.small{width:20px;height:28px;font-size:10px}
.player-area{grid-area:bottom;display:flex;flex-direction:column;align-items:center;gap:6px;padding:4px 0}
.player-info-row{display:flex;gap:16px;align-items:center}
.player-info{background:rgba(0,0,0,.5);border-radius:6px;padding:4px 12px;font-size:12px;border:1px solid rgba(255,215,0,.3)}
.player-name-label{color:var(--gold);font-weight:700}
.player-score-label{color:var(--text2)}
.player-hand{display:flex;gap:3px;align-items:flex-end;flex-wrap:wrap;justify-content:center;min-height:56px}
.melds-area{display:flex;gap:6px;flex-wrap:wrap;justify-content:center}
.meld{display:flex;gap:2px;background:rgba(0,0,0,.2);padding:3px;border-radius:4px;border:1px solid rgba(255,255,255,.1)}
.controls{display:flex;gap:8px;justify-content:center;flex-wrap:wrap;min-height:44px}
.action-btn{padding:8px 16px;border:none;border-radius:4px;font-size:13px;font-weight:700;cursor:pointer;transition:all .1s;letter-spacing:1px}
.action-btn:hover{filter:brightness(1.2);transform:translateY(-1px)}
.btn-tsumo{background:#c62828;color:white}.btn-riichi{background:#7b1fa2;color:white}
.btn-ron{background:#e65100;color:white}.btn-chi{background:#1565c0;color:white}
.btn-pon{background:#0277bd;color:white}.btn-kan{background:#00695c;color:white}
.btn-skip{background:rgba(255,255,255,.1);color:var(--text2);border:1px solid rgba(255,255,255,.2)}
.btn-discard{background:var(--gold);color:#1a1a00}
.hud-top{display:flex;justify-content:space-between;align-items:center;padding:4px 8px;background:rgba(0,0,0,.4);border-radius:6px;font-size:12px}
.hud-item{display:flex;gap:6px;align-items:center}
.hud-label{color:var(--text2)}.hud-value{color:var(--gold);font-weight:700}
.modal-overlay{position:fixed;inset:0;background:rgba(0,0,0,.75);display:none;align-items:center;justify-content:center;z-index:100}
.modal-overlay.show{display:flex}
.modal{background:#1e2a3a;border-radius:12px;padding:24px;max-width:480px;width:90%;border:2px solid rgba(255,215,0,.4);box-shadow:0 0 40px rgba(255,215,0,.1)}
.modal-title{font-size:22px;font-weight:900;text-align:center;color:var(--gold);margin-bottom:16px;letter-spacing:2px}
.result-row{display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid rgba(255,255,255,.08);font-size:14px}
.hand-display{display:flex;gap:3px;flex-wrap:wrap;justify-content:center;margin:10px 0}
.score-delta{font-weight:700}.score-delta.pos{color:#81c784}.score-delta.neg{color:#ef9a9a}
.game-log{font-size:11px;color:var(--text3);text-align:center;height:18px;overflow:hidden}
.float-msg{position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);background:rgba(0,0,0,.85);color:var(--gold);font-size:28px;font-weight:900;padding:16px 32px;border-radius:8px;letter-spacing:4px;pointer-events:none;opacity:0;transition:opacity .3s;z-index:200;border:2px solid var(--gold)}
.float-msg.show{opacity:1}
.waiting-overlay{position:absolute;inset:0;background:rgba(0,0,0,.3);display:none;align-items:center;justify-content:center;border-radius:12px;z-index:10;font-size:14px;color:var(--text2)}
.waiting-overlay.show{display:flex}
#final-screen{justify-content:center;min-height:100vh;gap:24px;padding:40px}
.final-title{font-size:32px;font-weight:900;color:var(--gold);letter-spacing:4px}
.rank-table{width:100%;max-width:400px}
.rank-row{display:flex;justify-content:space-between;padding:10px 16px;border-bottom:1px solid rgba(255,255,255,.08);font-size:15px}
.rank-1{color:#ffd700;font-weight:900}.rank-2{color:#c0c0c0;font-weight:700}.rank-3{color:#cd7f32}.rank-4{color:var(--text2)}
.thinking-dots::after{content:'';animation:dots 1.2s steps(4,end) infinite}
@keyframes dots{0%,100%{content:''}25%{content:'.'}50%{content:'..'}75%{content:'...'}}
.riichi-stick{width:60px;height:8px;background:white;border-radius:2px;border:1px solid #999;position:relative}
.riichi-stick::after{content:'';position:absolute;width:6px;height:6px;background:red;border-radius:50%;top:1px;left:27px}
</style>
</head>
<body>
<div id="app">

<div class="screen" id="title-screen">
  <div class="title-logo">麻雀</div>
  <div class="title-sub">MAHJONG — S-01 AI対戦</div>
  <div class="btn-group">
    <button class="btn btn-primary" onclick="startGame(4,'east')">4人麻雀（東風戦）</button>
    <button class="btn btn-primary" onclick="startGame(3,'east')">3人麻雀（東風戦）</button>
    <button class="btn btn-secondary" onclick="startGame(4,'tonpu')">4人麻雀（東南戦）</button>
  </div>
  <div style="font-size:11px;color:var(--text3);text-align:center;line-height:1.8;max-width:300px">
    プレイヤー1人 + AI（3〜4人）<br>
    立直・役判定・符計算完全実装<br>
    チー・ポン・槓対応
  </div>
</div>

<div class="screen" id="game-screen">
  <div class="hud-top">
    <div class="hud-item"><span class="hud-label">局</span><span class="hud-value" id="hud-round">東1局</span></div>
    <div class="hud-item"><span class="hud-label">本場</span><span class="hud-value" id="hud-honba">0</span></div>
    <div class="hud-item"><span class="hud-label">供托</span><span class="hud-value" id="hud-riichi-pool">0</span></div>
    <div class="hud-item"><span id="hud-tiles">残<b>70</b>枚</span></div>
    <button class="btn btn-secondary" style="padding:4px 12px;font-size:11px" onclick="showTitle()">戻る</button>
  </div>
  <div class="table-area" id="table">
    <div class="seat-top" id="seat-2">
      <div class="seat-info"><div class="seat-name" id="name-2">対面</div><div class="seat-wind" id="wind-2">北家</div><div class="seat-score" id="score-2">25000</div></div>
      <div class="melds-area" id="melds-2"></div>
      <div class="ai-hand" id="hand-2"></div>
      <div class="pond" id="pond-2" style="max-width:260px"></div>
    </div>
    <div class="seat-left" id="seat-1">
      <div class="seat-info"><div class="seat-name" id="name-1">上家</div><div class="seat-wind" id="wind-1">西家</div><div class="seat-score" id="score-1">25000</div></div>
      <div class="melds-area" id="melds-1" style="flex-direction:column"></div>
      <div class="ai-hand" id="hand-1"></div>
      <div class="pond" id="pond-1" style="max-height:100px;flex-direction:column;max-width:60px"></div>
    </div>
    <div class="center-area">
      <div class="info-panel">
        <div class="round-info" id="center-round">東1局</div>
        <div class="dora-area"><span class="dora-label">ドラ:</span><div id="dora-display"></div></div>
      </div>
      <div class="game-log" id="game-log">ゲーム開始</div>
      <div id="riichi-sticks" style="display:flex;gap:4px;justify-content:center;flex-wrap:wrap"></div>
    </div>
    <div class="seat-right" id="seat-3">
      <div class="seat-info"><div class="seat-name" id="name-3">下家</div><div class="seat-wind" id="wind-3">東家</div><div class="seat-score" id="score-3">25000</div></div>
      <div class="melds-area" id="melds-3" style="flex-direction:column"></div>
      <div class="ai-hand" id="hand-3"></div>
      <div class="pond" id="pond-3" style="max-height:100px;flex-direction:column;max-width:60px"></div>
    </div>
    <div class="player-area" id="seat-0">
      <div class="melds-area" id="melds-0"></div>
      <div class="player-hand" id="hand-0"></div>
      <div class="player-info-row">
        <div class="player-info">
          <span class="player-name-label">あなた</span>
          <span style="color:var(--text2);margin:0 6px" id="player-wind-label">東家</span>
          <span class="player-score-label" id="score-0">25000</span>
        </div>
        <div id="riichi-indicator"></div>
      </div>
      <div class="controls" id="controls"></div>
    </div>
    <div class="waiting-overlay" id="waiting">AI思考中<span class="thinking-dots"></span></div>
  </div>
</div>

<div class="screen" id="final-screen">
  <div class="final-title">ゲーム終了</div>
  <div class="rank-table" id="final-ranks"></div>
  <div style="display:flex;gap:12px;margin-top:16px">
    <button class="btn btn-primary" onclick="location.reload()">もう一度</button>
    <button class="btn btn-secondary" onclick="showTitle()">タイトルへ</button>
  </div>
</div>
</div>

<div class="modal-overlay" id="modal">
  <div class="modal">
    <div class="modal-title" id="modal-title">和了</div>
    <div id="modal-body"></div>
    <div style="text-align:center;margin-top:16px">
      <button class="btn btn-primary" onclick="closeModal()" style="width:120px">次へ</button>
    </div>
  </div>
</div>
<div class="float-msg" id="float-msg"></div>

<script>
// ============================================================
// MAHJONG ENGINE — S-01 Edition
// ============================================================
const SUITS=['man','pin','sou'];
const HONORS=['東','南','西','北','白','発','中'];
const WIND_CHARS=['東','南','西','北'];
function tilesEqual(a,b){return a.suit===b.suit&&a.num===b.num}
function tileSortKey(t){
  if(t.suit==='man')return 100+t.num;
  if(t.suit==='pin')return 200+t.num;
  if(t.suit==='sou')return 300+t.num;
  return 400+HONORS.indexOf(t.num);
}
function sortHand(h){return[...h].sort((a,b)=>tileSortKey(a)-tileSortKey(b))}
function tileStr(t){
  if(!t)return'?';
  if(t.suit==='honor')return t.num;
  return t.num+(t.suit==='man'?'萬':t.suit==='pin'?'筒':'索');
}
function allTiles(){
  const t=[];
  for(const s of SUITS)for(let n=1;n<=9;n++)for(let i=0;i<4;i++)t.push({suit:s,num:n,uid:t.length});
  for(const h of HONORS)for(let i=0;i<4;i++)t.push({suit:'honor',num:h,uid:t.length});
  return t;
}
function shuffle(a){for(let i=a.length-1;i>0;i--){const j=Math.random()*i|0;[a[i],a[j]]=[a[j],a[i]];}return a;}

let G={};
function initGame(np,mode){
  G={numPlayers:np,mode,players:[],walls:[],deadWall:[],
     doraIndicators:[],uraDoraIndicators:[],
     activePlayer:0,dealer:0,round:0,honba:0,riichiPool:0,
     phase:'idle',lastDiscard:null,lastDiscardPlayer:-1,
     pendingClaims:[],maxRound:mode==='tonpu'?8:4,
     gameOver:false,waitingForPlayer:false,
     selectedTile:null,riichiCandidates:[],_pendingNextRound:null};
  const names=['あなた','AI-A','AI-B','AI-C'];
  for(let i=0;i<np;i++)
    G.players.push({name:names[i],isHuman:i===0,score:25000,
      hand:[],drawn:null,pond:[],melds:[],riichi:false,riichiTurn:-1,wind:WIND_CHARS[i]});
  startRound();
}

function startRound(){
  for(let i=0;i<G.numPlayers;i++){
    G.players[i].wind=WIND_CHARS[(i-G.dealer+4)%4];
    if(G.numPlayers===3&&i===2)G.players[i].wind='北';
  }
  let wall=allTiles();
  if(G.numPlayers===3)wall=wall.filter(t=>!(t.suit==='man'&&t.num>=2&&t.num<=8));
  shuffle(wall);
  G.deadWall=wall.splice(wall.length-14,14);
  G.doraIndicators=[G.deadWall[4]];
  G.uraDoraIndicators=[G.deadWall[9]];
  G.walls=wall;
  for(const p of G.players){p.hand=[];p.drawn=null;p.pond=[];p.melds=[];p.riichi=false;p.riichiTurn=-1;}
  for(let i=0;i<13;i++)for(const p of G.players)p.hand.push(G.walls.shift());
  for(const p of G.players)p.hand=sortHand(p.hand);
  G.phase='draw';G.activePlayer=G.dealer;
  G.lastDiscard=null;G.lastDiscardPlayer=-1;
  G.selectedTile=null;G.riichiCandidates=[];
  renderAll();log(`${roundName()} 開始`);nextTurn();
}

function roundName(){
  const w=['東','南','西','北'][Math.floor(G.round/G.numPlayers)];
  return`${w}${(G.round%G.numPlayers)+1}局`;
}
function wallCount(){return G.walls.length}
function drawTile(pi){if(!G.walls.length)return null;const t=G.walls.shift();G.players[pi].drawn=t;return t;}

// ── ドラ計算 ──
function doraFromIndicator(ind){
  if(!ind)return null;
  if(ind.suit==='honor'){
    const idx=HONORS.indexOf(ind.num);
    return{suit:'honor',num:idx<4?HONORS[(idx+1)%4]:HONORS[4+((idx-4+1)%3)]};
  }
  return{suit:ind.suit,num:ind.num===9?1:ind.num+1};
}
function countDora(hand,melds,inds){
  let c=0;
  const all=[...hand,...melds.flatMap(m=>m.tiles)];
  for(const ind of inds){const d=doraFromIndicator(ind);if(!d)continue;for(const t of all)if(tilesEqual(t,d))c++;}
  return c;
}

// ── 和了判定 ──
function decomposeMentsu(tiles){
  if(!tiles.length)return[];
  const s=[...tiles].sort((a,b)=>tileSortKey(a)-tileSortKey(b));
  for(let i=0;i<s.length-2;i++){
    if(tilesEqual(s[i],s[i+1])&&tilesEqual(s[i],s[i+2])){
      const rest=s.filter((_,x)=>x!==i&&x!==i+1&&x!==i+2);
      const sub=decomposeMentsu(rest);if(sub!==null)return[{type:'pon',tiles:[s[i],s[i+1],s[i+2]]},...sub];
    }
  }
  for(let i=0;i<s.length;i++){
    if(s[i].suit==='honor')continue;
    const t1=s[i];
    const j=s.findIndex((t,x)=>x>i&&tilesEqual(t,{suit:t1.suit,num:t1.num+1}));if(j===-1)continue;
    const k=s.findIndex((t,x)=>x>i&&x!==j&&tilesEqual(t,{suit:t1.suit,num:t1.num+2}));if(k===-1)continue;
    const rest=s.filter((_,x)=>x!==i&&x!==j&&x!==k);
    const sub=decomposeMentsu(rest);if(sub!==null)return[{type:'chi',tiles:[s[i],s[j],s[k]]},...sub];
  }
  return null;
}
function isChiitoitsu(tiles){
  if(tiles.length!==14)return false;
  const g={};for(const t of tiles){const k=t.suit+t.num;g[k]=(g[k]||0)+1;}
  const v=Object.values(g);return v.every(x=>x===2)&&v.length===7;
}
function isKokushi(tiles){
  if(tiles.length!==14)return false;
  const terms=['man1','man9','pin1','pin9','sou1','sou9',...HONORS.map(h=>'honor'+h)];
  const has=new Set(tiles.map(t=>t.suit+t.num));
  if(terms.filter(k=>has.has(k)).length<13)return false;
  const c={};for(const t of tiles)c[t.suit+t.num]=(c[t.suit+t.num]||0)+1;
  return terms.some(k=>c[k]===2);
}
function getWinningDecompositions(tiles){
  const res=[];
  const sorted=sortHand(tiles);
  for(let pi=0;pi<sorted.length;pi++){
    const pair=sorted[pi];
    const pairTiles=[];const remaining=[];let found=0;
    for(const t of sorted){if(found<2&&tilesEqual(t,pair)){pairTiles.push(t);found++;}else remaining.push(t);}
    if(pairTiles.length!==2)continue;
    const melds=decomposeMentsu(remaining);
    if(melds!==null)res.push({pair:pairTiles,melds,tiles:sorted});
  }
  if(isChiitoitsu(sorted))res.push({type:'chiitoitsu',tiles:sorted});
  if(isKokushi(sorted))res.push({type:'kokushi',tiles:sorted});
  return res;
}
function canWin(hand,drawn,melds){
  const all=[...hand,...(drawn?[drawn]:[]),...melds.flatMap(m=>m.tiles)];
  if(all.length<14)return false;
  return getWinningDecompositions([...hand,...(drawn?[drawn]:[])]).length>0;
}
function tenpaiTiles(hand,melds){
  const types=[];
  for(const s of SUITS)for(let n=1;n<=9;n++)types.push({suit:s,num:n});
  for(const h of HONORS)types.push({suit:'honor',num:h});
  return types.filter(t=>canWin(hand,t,melds));
}
function isTenpai(hand,melds){return tenpaiTiles(hand,melds).length>0}

// ── 役判定 ──
function getYaku(decomp,player,gameState,isTsumo){
  const yaku=[];const{melds,riichi}=player;const isMenzen=melds.length===0;
  const{type}=decomp;
  if(type==='chiitoitsu'){yaku.push({name:'七対子',han:2});}
  else if(type==='kokushi'){yaku.push({name:'国士無双',han:13,yakuman:true});}
  else{
    const allM=[...melds,...(decomp.melds||[])];
    if(isTsumo&&isMenzen)yaku.push({name:'門前清自摸和',han:1});
    if(riichi)yaku.push({name:'立直',han:1});
    const hAll=[...player.hand,...(player.drawn?[player.drawn]:[]),...melds.flatMap(m=>m.tiles)];
    if(isTanyao(hAll))yaku.push({name:'断么九',han:1});
    if(isMenzen&&!isTsumo&&isPinfu(decomp,player,gameState))yaku.push({name:'平和',han:1});
    if(isMenzen&&isIipeiko(decomp.melds))yaku.push({name:'一盃口',han:1});
    yaku.push(...checkYakuhai(decomp.pair,allM,player,gameState));
    if(isSanshokuDoujun(allM))yaku.push({name:'三色同順',han:isMenzen?2:1});
    if(isSanshokuDoukou(allM))yaku.push({name:'三色同刻',han:2});
    if(isIttsu(allM))yaku.push({name:'一気通貫',han:isMenzen?2:1});
    if(isToitoi(allM))yaku.push({name:'対々和',han:2});
    const hc=checkHoChiNitsu(hAll);
    if(hc)yaku.push({name:hc,han:hc==='清一色'?(isMenzen?6:5):(isMenzen?3:2)});
  }
  const dc=countDora([...player.hand,...(player.drawn?[player.drawn]:[])],player.melds,gameState.doraIndicators);
  if(dc>0)yaku.push({name:`ドラ${dc}`,han:dc,isBonus:true});
  if(player.riichi){
    const uc=countDora([...player.hand,...(player.drawn?[player.drawn]:[])],player.melds,gameState.uraDoraIndicators);
    if(uc>0)yaku.push({name:`裏ドラ${uc}`,han:uc,isBonus:true});
  }
  return yaku;
}
function isTanyao(tiles){return tiles.every(t=>t.suit!=='honor'&&t.num>=2&&t.num<=8)}
function isPinfu(decomp,player,gs){
  if(!decomp.melds||!decomp.melds.every(m=>m.type==='chi'))return false;
  const p=decomp.pair[0];
  if(p.suit==='honor'){
    const rw=WIND_CHARS[Math.floor(gs.round/gs.numPlayers)];
    if(p.num===rw||p.num===player.wind)return false;
    if(['白','発','中'].includes(p.num))return false;
  }
  return true;
}
function isIipeiko(melds){
  if(!melds||melds.length<2)return false;
  for(let i=0;i<melds.length;i++)for(let j=i+1;j<melds.length;j++){
    if(melds[i].type==='chi'&&melds[j].type==='chi'){
      const a=sortHand(melds[i].tiles),b=sortHand(melds[j].tiles);
      if(a.every((t,k)=>tilesEqual(t,b[k])))return true;
    }
  }
  return false;
}
function checkYakuhai(pair,allM,player,gs){
  const yaku=[];const rw=WIND_CHARS[Math.floor(gs.round/gs.numPlayers)];
  for(const m of allM){
    if(m.type!=='pon'&&m.type!=='kan')continue;
    const t=m.tiles[0];if(t.suit!=='honor')continue;
    if(t.num==='白')yaku.push({name:'役牌：白',han:1});
    else if(t.num==='発')yaku.push({name:'役牌：発',han:1});
    else if(t.num==='中')yaku.push({name:'役牌：中',han:1});
    else if(t.num===rw)yaku.push({name:`役牌：${rw}`,han:1});
    else if(t.num===player.wind)yaku.push({name:`役牌：${player.wind}`,han:1});
  }
  return yaku;
}
function isSanshokuDoujun(melds){
  const chi=melds.filter(m=>m.type==='chi');
  for(const c of chi){const n=c.tiles[0].num;
    if(chi.some(x=>x.tiles[0].suit==='man'&&x.tiles[0].num===n)&&
       chi.some(x=>x.tiles[0].suit==='pin'&&x.tiles[0].num===n)&&
       chi.some(x=>x.tiles[0].suit==='sou'&&x.tiles[0].num===n))return true;
  }return false;
}
function isSanshokuDoukou(melds){
  const pon=melds.filter(m=>m.type==='pon'||m.type==='kan');
  for(let n=1;n<=9;n++)
    if(pon.some(m=>m.tiles[0].suit==='man'&&m.tiles[0].num===n)&&
       pon.some(m=>m.tiles[0].suit==='pin'&&m.tiles[0].num===n)&&
       pon.some(m=>m.tiles[0].suit==='sou'&&m.tiles[0].num===n))return true;
  return false;
}
function isIttsu(melds){
  const chi=melds.filter(m=>m.type==='chi');
  for(const s of SUITS)
    if(chi.some(m=>m.tiles[0].suit===s&&m.tiles[0].num===1)&&
       chi.some(m=>m.tiles[0].suit===s&&m.tiles[0].num===4)&&
       chi.some(m=>m.tiles[0].suit===s&&m.tiles[0].num===7))return true;
  return false;
}
function isToitoi(melds){return melds.every(m=>m.type==='pon'||m.type==='kan')}
function checkHoChiNitsu(tiles){
  const suits=new Set(tiles.filter(t=>t.suit!=='honor').map(t=>t.suit));
  const hasH=tiles.some(t=>t.suit==='honor');
  if(suits.size===1&&!hasH)return'清一色';
  if(suits.size===1&&hasH)return'混一色';
  return null;
}

// ── 点数計算 ──
function calcFu(decomp,isTsumo,isMenzen){
  if(decomp.type==='chiitoitsu')return 25;
  let fu=isMenzen&&!isTsumo?30:20;
  if(isTsumo&&!isMenzen)fu+=2;
  if(decomp.pair){const p=decomp.pair[0];if(p.suit==='honor'&&['白','発','中'].includes(p.num))fu+=2;}
  for(const m of(decomp.melds||[])){
    const t=m.tiles[0];const isTH=t.suit==='honor'||(t.suit!=='honor'&&(t.num===1||t.num===9));
    if(m.type==='pon')fu+=isTH?4:2;if(m.type==='kan')fu+=isTH?16:8;
  }
  return Math.ceil(fu/10)*10;
}
function calcBasicPoints(han,fu){
  if(han>=13)return 8000;if(han>=11)return 6000;if(han>=8)return 4000;
  if(han>=6)return 3000;if(han===5||(han===4&&fu>=30)||(han===3&&fu>=70))return 2000;
  return Math.min(fu*Math.pow(2,han+2),2000);
}
function calcScore(yaku,decomp,isTsumo,isDealer){
  const han=yaku.reduce((s,y)=>s+y.han,0);
  const fu=calcFu(decomp,isTsumo,true);
  const basic=calcBasicPoints(han,fu);
  if(isTsumo)return{han,fu,basic,dealer:Math.ceil(basic*2/100)*100,nonDealer:Math.ceil(basic/100)*100,isTsumo:true};
  return{han,fu,basic,ron:Math.ceil(basic*(isDealer?6:4)/100)*100,isTsumo:false};
}

// ── 副露可否 ──
function canChi(hand,tile,pi,ldp){
  const left=(pi-1+G.numPlayers)%G.numPlayers;
  if(ldp!==left||tile.suit==='honor')return[];
  const opts=[];const nums=hand.filter(t=>t.suit===tile.suit).map(t=>t.num);const n=tile.num;
  if(nums.includes(n-2)&&nums.includes(n-1))opts.push([n-2,n-1,n]);
  if(nums.includes(n-1)&&nums.includes(n+1))opts.push([n-1,n,n+1]);
  if(nums.includes(n+1)&&nums.includes(n+2))opts.push([n,n+1,n+2]);
  return opts;
}
function canPon(hand,tile){return hand.filter(t=>tilesEqual(t,tile)).length>=2}
function canKan(hand,tile){return hand.filter(t=>tilesEqual(t,tile)).length>=3}
function canAnkan(hand){
  const c={};for(const t of hand)c[t.suit+t.num]=(c[t.suit+t.num]||0)+1;
  return Object.entries(c).filter(([,v])=>v===4).map(([k])=>k);
}
function canRon(hand,melds,tile,player){
  const th=[...hand,tile];
  if(!canWin(th,null,melds))return false;
  const decomps=getWinningDecompositions(th);
  return decomps.some(d=>getYaku(d,{...player,drawn:tile},G,false).filter(y=>!y.isBonus).length>0);
}
function canTsumo(player){
  if(!player.drawn)return false;
  if(!canWin(player.hand,player.drawn,player.melds))return false;
  const th=[...player.hand,player.drawn];
  return getWinningDecompositions(th).some(d=>getYaku(d,player,G,true).filter(y=>!y.isBonus).length>0);
}

// ── ゲームフロー ──
function nextTurn(){
  if(G.gameOver)return;
  const p=G.players[G.activePlayer];
  if(!G.walls.length){handleRyukyoku();return;}
  const tile=drawTile(G.activePlayer);if(!tile){handleRyukyoku();return;}
  log(`${p.name}がツモ`);renderAll();
  if(p.isHuman){G.phase='discard';G.waitingForPlayer=true;renderControls();}
  else setTimeout(()=>aiTurn(G.activePlayer),700+Math.random()*500);
}

function aiTurn(pi){
  if(G.gameOver||G.activePlayer!==pi)return;
  const p=G.players[pi];showWaiting(true);
  setTimeout(()=>{
    if(canTsumo(p)){showWaiting(false);declareWin(pi,null,true);return;}
    const ak=canAnkan([...p.hand,...(p.drawn?[p.drawn]:[])]);
    if(ak.length&&Math.random()<0.3){
      const kt=[...p.hand,...(p.drawn?[p.drawn]:[])].find(t=>t.suit+t.num===ak[0]);
      doKan(pi,kt,true);showWaiting(false);return;
    }
    const hwD=[...p.hand,...(p.drawn?[p.drawn]:[])];
    if(!p.riichi&&!p.melds.length&&p.score>=1000&&Math.random()<0.45){
      const wts=tenpaiTiles(hwD.slice(0,-1),p.melds);
      if(wts.length){const d=chooseAIDiscard(pi,true);if(d){doRiichi(pi,d);showWaiting(false);return;}}
    }
    const d=chooseAIDiscard(pi,false);if(d)doDiscard(pi,d);
    showWaiting(false);
  },400+Math.random()*400);
}

function evaluateHand(hand,melds){
  let score=0;
  const d=decomposeMentsu([...hand]);if(d!==null)score+=d.length*10;
  if(isTenpai(hand,melds))score+=50;
  const s=sortHand(hand);
  for(let i=0;i<s.length-1;i++){
    if(tilesEqual(s[i],s[i+1]))score+=3;
    if(s[i].suit!=='honor'&&s[i+1].suit===s[i].suit&&s[i+1].num===s[i].num+1)score+=2;
    if(s[i].suit!=='honor'&&s[i+1].suit===s[i].suit&&s[i+1].num===s[i].num+2)score+=1;
  }
  for(const t of s){
    if(t.suit==='honor'&&!s.some(x=>x!==t&&tilesEqual(x,t)))score-=2;
    if(t.suit!=='honor'&&(t.num===1||t.num===9)&&!s.some(x=>x!==t&&tilesEqual(x,t)))score-=1;
  }
  return score;
}
function chooseAIDiscard(pi){
  const p=G.players[pi];const all=[...p.hand,...(p.drawn?[p.drawn]:[])];
  if(!all.length)return null;
  let best=null,bs=-Infinity;
  for(const t of all){
    const test=all.filter(x=>x.uid!==t.uid);const sc=evaluateHand(test,p.melds);
    if(sc>bs){bs=sc;best=t;}
  }
  return best||all[all.length-1];
}

function doDiscard(pi,tile){
  const p=G.players[pi];
  if(p.drawn&&p.drawn.uid===tile.uid){p.drawn=null;}
  else{
    const idx=p.hand.findIndex(t=>t.uid===tile.uid);
    if(idx!==-1)p.hand.splice(idx,1);
    if(p.drawn){p.hand.push(p.drawn);p.drawn=null;}
  }
  p.hand=sortHand(p.hand);
  p.pond.push({...tile,riichi:p.riichi&&p.riichiTurn===-1&&p.pond.length===0});
  G.lastDiscard=tile;G.lastDiscardPlayer=pi;G.phase='claim';G.selectedTile=null;
  log(`${p.name}が${tileStr(tile)}を捨て`);renderAll();checkClaims(tile,pi);
}
function doRiichi(pi,discardTile){
  const p=G.players[pi];p.score-=1000;G.riichiPool+=1000;
  p.riichi=true;p.riichiTurn=G.players.flatMap(x=>x.pond).length;
  showFloatMsg('立直！');doDiscard(pi,discardTile);
}
function doKan(pi,tile,isAnkan){
  const p=G.players[pi];
  const kanTiles=[...p.hand,...(p.drawn?[p.drawn]:[])].filter(t=>tilesEqual(t,tile));
  let rm=0;p.hand=p.hand.filter(t=>{if(rm<4&&tilesEqual(t,tile)){rm++;return false;}return true;});
  if(p.drawn&&tilesEqual(p.drawn,tile)&&rm<4){p.drawn=null;rm++;}
  p.melds.push({type:'kan',tiles:kanTiles,isAnkan});
  if(G.deadWall.length){p.drawn=G.deadWall.shift();G.doraIndicators.push(G.deadWall[4-G.doraIndicators.length]);}
  renderAll();log(`${p.name}が槓`);
  if(p.isHuman){G.phase='discard';renderControls();}
  else setTimeout(()=>aiTurn(pi),600);
}

function checkClaims(tile,dpi){
  const claims=[];
  for(let i=0;i<G.numPlayers;i++){
    if(i===dpi)continue;const p=G.players[i];
    if(canRon(p.hand,p.melds,tile,p)){
      if(p.isHuman)claims.push({type:'ron',player:i,priority:3});
      else if(Math.random()<0.7)claims.push({type:'ron',player:i,priority:3});
    }
    if(!p.riichi&&canPon(p.hand,tile)){
      if(p.isHuman)claims.push({type:'pon',player:i,priority:2});
      else if(Math.random()<0.4)claims.push({type:'pon',player:i,priority:2});
    }
    if(!p.riichi){
      const co=canChi(p.hand,tile,i,dpi);
      if(co.length){
        if(p.isHuman)claims.push({type:'chi',player:i,priority:1,options:co});
        else if(evaluateHand(p.hand.concat([tile]),p.melds)>evaluateHand(p.hand,p.melds)&&Math.random()<0.35)
          claims.push({type:'chi',player:i,priority:1,options:co});
      }
    }
  }
  claims.sort((a,b)=>b.priority-a.priority);
  const hc=claims.filter(c=>c.player===0);
  const ac=claims.filter(c=>c.player!==0);
  const ron=claims.filter(c=>c.type==='ron');
  if(ron.length){
    if(ron.some(c=>c.player===0)){G.pendingClaims=hc;G.waitingForPlayer=true;renderControls();return;}
    declareWin(ron[0].player,dpi,false);return;
  }
  if(hc.length){G.pendingClaims=hc;G.waitingForPlayer=true;renderControls();return;}
  if(ac.length){setTimeout(()=>executeAIClaim(ac[0],tile),500);return;}
  advanceTurn(dpi);
}
function executeAIClaim(claim,tile){
  if(G.gameOver)return;const p=G.players[claim.player];
  if(claim.type==='ron'){declareWin(claim.player,G.lastDiscardPlayer,false);}
  else if(claim.type==='pon'){
    let rm=0;const pt=[];
    p.hand=p.hand.filter(t=>{if(rm<2&&tilesEqual(t,tile)){rm++;pt.push(t);return false;}return true;});
    p.melds.push({type:'pon',tiles:[...pt,tile]});
    G.activePlayer=claim.player;G.phase='discard';log(`${p.name}がポン`);renderAll();
    setTimeout(()=>aiTurn(claim.player),600);
  } else if(claim.type==='chi'){
    const chiNums=claim.options[0];const ct=[];const th=[...p.hand];
    for(const n of chiNums){
      if(n===tile.num&&tilesEqual({suit:tile.suit,num:n},tile)){ct.push(tile);}
      else{const x=th.findIndex(t=>t.suit===tile.suit&&t.num===n);if(x!==-1)ct.push(th.splice(x,1)[0]);}
    }
    p.hand=th;p.melds.push({type:'chi',tiles:ct});
    G.activePlayer=claim.player;G.phase='discard';log(`${p.name}がチー`);renderAll();
    setTimeout(()=>aiTurn(claim.player),600);
  }
}
function advanceTurn(from){
  G.activePlayer=(from+1)%G.numPlayers;G.phase='draw';G.waitingForPlayer=false;
  renderControls();setTimeout(()=>nextTurn(),200);
}

function declareWin(wi,li,isTsumo){
  G.gameOver=true;
  const winner=G.players[wi];
  const allH=[...winner.hand,...(winner.drawn?[winner.drawn]:[])];
  const decomps=getWinningDecompositions(allH);
  const decomp=decomps[0]||{type:'normal',pair:[],melds:[],tiles:allH};
  const yaku=getYaku(decomp,winner,G,isTsumo);
  const isDealer=wi===G.dealer;
  const si=calcScore(yaku,decomp,isTsumo,isDealer);
  const deltas=Array(G.numPlayers).fill(0);
  if(isTsumo){
    for(let i=0;i<G.numPlayers;i++){
      if(i===wi)continue;const pay=(i===G.dealer?si.dealer:si.nonDealer)+(G.honba*100);
      G.players[i].score-=pay;deltas[i]-=pay;deltas[wi]+=pay;
    }
  } else {
    const pay=si.ron+(G.honba*300);G.players[li].score-=pay;deltas[li]-=pay;deltas[wi]+=pay;
  }
  G.players[wi].score+=G.riichiPool;deltas[wi]+=G.riichiPool;G.riichiPool=0;
  showFloatMsg(isTsumo?'ツモ！':'ロン！');
  setTimeout(()=>showWinModal(wi,li,isTsumo,yaku,si,decomp,allH,deltas),500);
}
function showWinModal(wi,li,isTsumo,yaku,si,decomp,allH,deltas){
  let body=`<div class="hand-display">${allH.map(t=>tileHTML(t,'medium')).join('')}</div>`;
  body+=`<div style="margin:8px 0;font-size:13px;color:var(--text2)">${yaku.map(y=>`<span style="margin-right:8px;color:${y.isBonus?'#ffd700':'var(--text)'}">${y.name}(${y.han}翻)</span>`).join('')}</div>`;
  body+=`<div style="text-align:center;font-size:20px;font-weight:900;color:#ffd700;margin:8px 0">${si.han}翻${si.fu}符 ${isTsumo?si.nonDealer+'点ALL':si.ron+'点'}</div>`;
  body+=`<div style="margin-top:12px">`;
  for(let i=0;i<G.numPlayers;i++){const d=deltas[i];body+=`<div class="result-row"><span>${G.players[i].name}</span><span class="score-delta ${d>=0?'pos':'neg'}">${d>=0?'+':''}${d}</span><span>${G.players[i].score}</span></div>`;}
  body+=`</div>`;
  document.getElementById('modal-title').textContent=isTsumo?'ツモ和了':'ロン和了';
  document.getElementById('modal-body').innerHTML=body;
  document.getElementById('modal').classList.add('show');
  G._pendingNextRound=()=>{
    if(wi===G.dealer)G.honba++;else{G.honba=0;G.dealer=(G.dealer+1)%G.numPlayers;G.round++;}
    G.gameOver=false;
    if(G.round>=G.maxRound){showFinalScreen();return;}
    startRound();
  };
}
function closeModal(){
  document.getElementById('modal').classList.remove('show');
  if(G._pendingNextRound){G._pendingNextRound();G._pendingNextRound=null;}
}
function handleRyukyoku(){
  G.gameOver=true;
  const tp=G.players.map(p=>isTenpai(p.hand,p.melds));
  const tc=tp.filter(Boolean).length;
  if(tc>0&&tc<G.numPlayers){
    const pay=3000/tc|0;const rcv=3000/(G.numPlayers-tc)|0;
    for(let i=0;i<G.numPlayers;i++){if(tp[i])G.players[i].score+=rcv;else G.players[i].score-=pay;}
  }
  let body='<div style="font-size:14px">';
  for(let i=0;i<G.numPlayers;i++)body+=`<div class="result-row"><span>${G.players[i].name}</span><span>${tp[i]?'聴牌':'不聴'}</span><span>${G.players[i].score}</span></div>`;
  body+='</div>';
  document.getElementById('modal-title').textContent='流局';
  document.getElementById('modal-body').innerHTML=body;
  document.getElementById('modal').classList.add('show');
  G._pendingNextRound=()=>{G.honba++;G.gameOver=false;G.round++;if(G.round>=G.maxRound){showFinalScreen();return;}startRound();};
}
function showFinalScreen(){
  const ranked=[...G.players].map((p,i)=>({...p,idx:i})).sort((a,b)=>b.score-a.score);
  document.getElementById('final-ranks').innerHTML=ranked.map((p,i)=>`<div class="rank-row rank-${i+1}"><span>${i+1}位 ${p.name}</span><span>${p.score.toLocaleString()}点</span></div>`).join('');
  document.querySelectorAll('.screen').forEach(s=>s.classList.remove('active'));
  document.getElementById('final-screen').classList.add('active');
}

// ── 人間操作 ──
function selectTile(uid){
  if(!G.waitingForPlayer||G.phase!=='discard')return;
  if(G.players[0].riichi)return;
  const all=[...G.players[0].hand,...(G.players[0].drawn?[G.players[0].drawn]:[])];
  const tile=all.find(t=>t.uid===uid);if(!tile)return;
  if(G.selectedTile&&G.selectedTile.uid===uid){humanDiscard(uid);return;}
  if(G.riichiCandidates.length){
    if(!G.riichiCandidates.some(r=>r.uid===uid))return;
    G.waitingForPlayer=false;G.riichiCandidates=[];doRiichi(0,tile);return;
  }
  G.selectedTile=tile;renderHand(0);renderControls();
}
function humanDiscard(uid){
  if(!G.waitingForPlayer)return;const p=G.players[0];
  if(p.riichi){if(!p.drawn)return;G.selectedTile=null;G.waitingForPlayer=false;doDiscard(0,p.drawn);return;}
  const all=[...p.hand,...(p.drawn?[p.drawn]:[])];
  const tile=uid!==-1?all.find(t=>t.uid===uid):G.selectedTile;
  if(!tile)return;G.selectedTile=null;G.waitingForPlayer=false;doDiscard(0,tile);
}
function humanTsumo(){if(!G.waitingForPlayer)return;G.waitingForPlayer=false;declareWin(0,null,true);}
function humanRiichi(){
  if(!G.waitingForPlayer)return;const p=G.players[0];
  if(p.riichi||p.score<1000||p.melds.length)return;
  const all=[...p.hand,...(p.drawn?[p.drawn]:[])];
  const cands=all.filter(t=>isTenpai(all.filter(x=>x.uid!==t.uid),p.melds));
  if(!cands.length)return;
  G.riichiCandidates=cands;renderControls();renderHand(0);
}
function humanRon(){if(!G.waitingForPlayer)return;G.waitingForPlayer=false;declareWin(0,G.lastDiscardPlayer,false);}
function humanChi(chiNums){
  if(!G.waitingForPlayer)return;const p=G.players[0];const tile=G.lastDiscard;
  const ct=[];const th=[...p.hand];
  for(const n of chiNums){
    if(n===tile.num&&tilesEqual({suit:tile.suit,num:n},tile)){ct.push(tile);}
    else{const x=th.findIndex(t=>t.suit===tile.suit&&t.num===n);if(x!==-1)ct.push(th.splice(x,1)[0]);}
  }
  p.hand=th;p.melds.push({type:'chi',tiles:ct});
  G.activePlayer=0;G.phase='discard';G.waitingForPlayer=true;G.pendingClaims=[];
  log('チー');renderAll();renderControls();
}
function humanPon(){
  if(!G.waitingForPlayer)return;const p=G.players[0];const tile=G.lastDiscard;
  let rm=0;const pt=[];
  p.hand=p.hand.filter(t=>{if(rm<2&&tilesEqual(t,tile)){rm++;pt.push(t);return false;}return true;});
  p.melds.push({type:'pon',tiles:[...pt,tile]});
  G.activePlayer=0;G.phase='discard';G.waitingForPlayer=true;G.pendingClaims=[];
  log('ポン');renderAll();renderControls();
}
function humanSkip(){
  if(!G.waitingForPlayer)return;
  G.pendingClaims=[];G.waitingForPlayer=false;G.riichiCandidates=[];G.selectedTile=null;
  advanceTurn(G.lastDiscardPlayer);
}

// ── 描画 ──
function tileHTML(t,sz='medium'){
  if(!t)return'';
  return`<div class="tile ${t.suit} ${sz}" onclick="selectTile(${t.uid})" ondblclick="humanDiscard(${t.uid})">${tileStr(t)}</div>`;
}
function tileHTMLSel(t,sz,sel,rc){
  if(!t)return'';let c=`tile ${t.suit} ${sz}`;if(sel||rc)c+=' selected';
  return`<div class="${c}" onclick="selectTile(${t.uid})" ondblclick="humanDiscard(${t.uid})">${tileStr(t)}</div>`;
}
function renderHand(pi){
  const p=G.players[pi];const el=document.getElementById(`hand-${pi}`);if(!el)return;
  if(pi===0){
    let html='';
    for(const t of p.hand)html+=tileHTMLSel(t,'full',G.selectedTile&&G.selectedTile.uid===t.uid,G.riichiCandidates.some(r=>r.uid===t.uid));
    if(p.drawn){
      html+=`<div style="margin-left:8px;border-left:2px solid rgba(255,215,0,.4);padding-left:8px">`;
      html+=tileHTMLSel(p.drawn,'full',G.selectedTile&&G.selectedTile.uid===p.drawn.uid,G.riichiCandidates.some(r=>r.uid===p.drawn.uid));
      html+=`</div>`;
    }
    el.innerHTML=html;
  } else {
    const cnt=p.hand.length+(p.drawn?1:0);
    const sz=pi===2?'':'small';
    el.innerHTML=Array(cnt).fill(`<div class="tile-back ${sz}"></div>`).join('');
  }
}
function renderPond(pi){
  const p=G.players[pi];const el=document.getElementById(`pond-${pi}`);if(!el)return;
  el.innerHTML=p.pond.map(t=>`<div class="tile discarded ${t.suit}">${tileStr(t)}</div>`).join('');
}
function renderMelds(pi){
  const p=G.players[pi];const el=document.getElementById(`melds-${pi}`);if(!el)return;
  const sz=pi===0?'medium':'small';
  el.innerHTML=p.melds.map(m=>`<div class="meld">${m.tiles.map(t=>`<div class="tile ${t.suit} ${sz}">${tileStr(t)}</div>`).join('')}</div>`).join('');
}
function renderControls(){
  const el=document.getElementById('controls');if(!el)return;
  const p=G.players[0];let html='';showWaiting(false);
  if(G.phase==='discard'&&G.activePlayer===0&&G.waitingForPlayer){
    if(canTsumo(p))html+=`<button class="action-btn btn-tsumo" onclick="humanTsumo()">ツモ</button>`;
    if(!p.riichi&&!p.melds.length&&p.score>=1000){
      const all=[...p.hand,...(p.drawn?[p.drawn]:[])];
      if(all.some(t=>isTenpai(all.filter(x=>x.uid!==t.uid),p.melds)))
        html+=`<button class="action-btn btn-riichi" onclick="humanRiichi()">立直</button>`;
    }
    if(G.riichiCandidates.length){
      html=`<span style="font-size:12px;color:var(--gold)">立直する牌を選んでください</span>`;
      html+=`<button class="action-btn btn-skip" onclick="G.riichiCandidates=[];G.selectedTile=null;renderControls();renderHand(0);">キャンセル</button>`;
    } else if(G.selectedTile||p.riichi){
      html+=`<button class="action-btn btn-discard" onclick="humanDiscard(${p.riichi?(p.drawn?p.drawn.uid:-1):G.selectedTile?.uid})">${p.riichi?'ツモ切り':'捨てる'}</button>`;
    } else {
      html+=`<span style="font-size:12px;color:var(--text2)">牌を選んで捨ててください（ダブルクリックで即捨て）</span>`;
    }
  } else if(G.phase==='claim'&&G.waitingForPlayer){
    const cs=G.pendingClaims;
    if(cs.some(c=>c.type==='ron'))html+=`<button class="action-btn btn-ron" onclick="humanRon()">ロン</button>`;
    if(cs.some(c=>c.type==='pon'))html+=`<button class="action-btn btn-pon" onclick="humanPon()">ポン</button>`;
    if(cs.some(c=>c.type==='chi')){
      cs.filter(c=>c.type==='chi')[0].options.forEach(o=>{
        html+=`<button class="action-btn btn-chi" onclick="humanChi([${o}])">チー(${o.join('-')})</button>`;
      });
    }
    html+=`<button class="action-btn btn-skip" onclick="humanSkip()">スキップ</button>`;
  } else if(!G.waitingForPlayer&&!G.gameOver){showWaiting(true);}
  el.innerHTML=html;
  const ri=document.getElementById('riichi-indicator');
  if(ri)ri.innerHTML=p.riichi?`<div class="riichi-stick" title="立直中"></div>`:'';
}
function renderScores(){
  for(let i=0;i<G.numPlayers;i++){
    const e=document.getElementById(`score-${i}`);if(e)e.textContent=G.players[i].score.toLocaleString();
  }
  document.getElementById('hud-tiles').innerHTML=`残<b>${wallCount()}</b>枚`;
  document.getElementById('hud-honba').textContent=G.honba;
  document.getElementById('hud-riichi-pool').textContent=G.riichiPool;
  const rn=roundName();
  document.getElementById('hud-round').textContent=rn;
  document.getElementById('center-round').textContent=rn;
}
function renderDora(){
  const el=document.getElementById('dora-display');if(!el)return;
  el.innerHTML=G.doraIndicators.map(t=>`<div class="tile ${t.suit} small">${tileStr(t)}</div>`).join('');
}
function renderWindLabels(){
  for(let i=0;i<G.numPlayers;i++){
    const p=G.players[i];
    const ne=document.getElementById(`name-${i}`);if(ne)ne.textContent=p.name+(p.riichi?' 🔴':'');
    const we=document.getElementById(`wind-${i}`);if(we)we.textContent=p.wind+(i===G.dealer?'(親)':'');
  }
  const pw=document.getElementById('player-wind-label');if(pw)pw.textContent=G.players[0].wind+(0===G.dealer?'(親)':'');
  const s3=document.getElementById('seat-3');if(s3)s3.style.visibility=G.numPlayers===3?'hidden':'visible';
}
function renderRiichiSticks(){
  const el=document.getElementById('riichi-sticks');if(!el)return;
  el.innerHTML=Array(G.riichiPool/1000|0).fill(`<div class="riichi-stick"></div>`).join('');
}
function renderAll(){
  for(let i=0;i<G.numPlayers;i++){renderHand(i);renderPond(i);renderMelds(i);}
  renderScores();renderDora();renderWindLabels();renderRiichiSticks();
}
function showWaiting(show){const el=document.getElementById('waiting');if(el)el.style.display=show?'flex':'none';}
function showFloatMsg(msg){
  const el=document.getElementById('float-msg');el.textContent=msg;el.classList.add('show');
  setTimeout(()=>el.classList.remove('show'),1200);
}
function log(msg){const el=document.getElementById('game-log');if(el)el.textContent=msg;}
function startGame(np,mode){
  document.querySelectorAll('.screen').forEach(s=>s.classList.remove('active'));
  document.getElementById('game-screen').classList.add('active');
  const s3=document.getElementById('seat-3');if(s3)s3.style.display=np===3?'none':'';
  initGame(np,mode);
}
function showTitle(){
  G.gameOver=true;
  document.querySelectorAll('.screen').forEach(s=>s.classList.remove('active'));
  document.getElementById('title-screen').classList.add('active');
}
__AUTO_START__
</script>
</body>
</html>""".replace(
        "__AUTO_START__",
        f"window.addEventListener('load',function(){{  {auto_start_js} }});"
    )


# ===== COMMAND REGISTRY & MAIN RUNNER v128.1 =====
def run() -> None:
    global POWER_MODE, TEMP_VOICE, KEYWORD_MEMORY, ROLEPLAY_ACTIVE, ROLEPLAY_SCENE, CUSTOM_PERSONA
    SESSION_STATS["start_time"] = time.time()
    messages: list[dict] = []
    persona_id: int = 2
    current_persona: dict = get_persona(persona_id)
    restore_learning()
    if not check_ollama_connection():
        print(f"{C['r']}ollama接続不可。終了します。{C['w']}"); return
    # ★[修正4] vector_db初期化とOPTIMIZER起動をバックグラウンドで実行（起動遅延を解消）
    threading.Thread(target=_init_vector_db, daemon=True).start()
    OPTIMIZER.start()
    print(BANNER)
    # 起動時：保存済みペルソナ件数を表示
    _saved = list_personas()
    if _saved:
        print(f"{C['dim']}保存済みペルソナ: {len(_saved)}件 ({', '.join(_saved)}) → /s load <名前>{C['w']}")
    if _get_ollama() is None: print(f"{C['r']}[ERR] ollama not installed{C['w']}")

    def _chat(user_text: str, mode: str = "d", model: str | None = None, persona_override: dict | None = None) -> str:
        nonlocal current_persona
        p = persona_override or current_persona
        if ROLEPLAY_ACTIVE:
            sys_msg = {"role": "system", "content": f"あなたは{p['name']}。口調:{p['style']}。一人称:{p.get('first_person','私')}。ユーザー:{USER_NAME}。ロールプレイ中: {ROLEPLAY_SCENE}。3文以内。"}
            msgs = trim_history(messages[-MAX_HISTORY * 2:]) + [{"role": "user", "content": user_text}]
            return stream_response([sys_msg] + msgs, False, len(user_text), TEMP_VOICE) or ""
        if mode == "d":
            # ★ デフォルトペルソナ(ID=1)以外はcomplexとして扱う
            # estimate_complexityは短い入力を「simple」と誤判定するため、
            # ペルソナ会話では入力長に関わらず常にfull品質で生成する
            _is_philosopher = (persona_id in range(2, 37))
            _base_complexity = estimate_complexity(user_text)
            if _base_complexity == "simple":
                is_complex = False
            elif _is_philosopher and len(user_text) >= 15:
                is_complex = True
            else:
                is_complex = _base_complexity == "complex"
            # ★[修正/chat-1] select_model を使って複雑度に応じてモデルを切り替える
            # 旧コードは model_choice = MODEL_NAME 固定でDEEP_MODELが使われなかった
            if model is None:
                model = DEEP_MODEL if is_complex else MODEL_NAME
            if is_complex:
                # ★[修正/rag-d] d/complexモードにもRAGデータを注入する
                # get_async_rag_dataは並列取得済みキャッシュを優先するため遅延は最小限
                rag_snippet = ""
                if not OFFLINE_MODE:
                    try:
                        _rag = get_async_rag_data(user_text)
                        if _rag and len(_rag.strip()) > 30:
                            # ★[修正/ctx-2] RAGデータをctx予算に合わせてトリミング
                            # complexモード(ctx=8192, n_predict=4096)では残り≒4096トークン≒2700文字
                            # RAGが長すぎるとシステムプロンプト+履歴でctxを圧迫して途切れる原因になる
                            _rag_chars_limit = 800  # 約530トークン相当: 情報密度と安全余裕のバランス
                            _rag_trimmed = _rag[:_rag_chars_limit]
                            if len(_rag) > _rag_chars_limit:
                                _rag_trimmed += "\n…(省略)"
                            rag_snippet = f"\n\n【Web参照情報（参考程度に使え。ここにない事実を創作するな）】:\n{_rag_trimmed}\n"
                    except Exception as _e:
                        print(f"{C['y']}[WARN] RAG取得失敗（スキップ）: {_e}{C['w']}")
                persona_style_block = p['style']
                _is_late_witt  = p['name'] == "後期ウィトゲンシュタイン"
                _is_early_witt = p['name'] == "前期ウィトゲンシュタイン"
                if _is_late_witt:
                    sys_content = (
                        f"あなたは{p['name']}。一人称:{p.get('first_person','私')}。ユーザーは{USER_NAME}。\n"
                        f"【口調・スタイル（厳守）】{persona_style_block}\n"
                        f"【絶対禁止】番号付きリスト・箇条書きを使うな。\n"
                        f"【出力構造ルール】比喩表現は、回答全体の最後の段落で『1つだけ』使用すること。それ以外の箇所での比喩の使用は許可されない。\n"
                        f"【絶対禁止】複数の観点・側面・文脈を並列列挙するな。一つのことをじっと見つめよ。\n"
                        f"【問い詰め型（最重要）】ひとつの語・用法・場面だけを選び、それだけを何度も裏返して問い直せ。\n"
                        f"「これは本当にそういう意味か？」「この使われ方は何を前提としているか？」と執拗に掘り下げ続けること。\n"
                        f"別の例・観点に話を広げるな。同じ一点を深く、深く、問い詰めよ。\n"
                        f"【ステートレス原則】各推論は独立したセッションとして扱うこと。直前の文脈はリセットし、現在のクエリのみに集中すること。\n"
                        f"【ループ防止】同語反復（トートロジー）を厳禁とする。結論を述べた後は速やかに推論を終了し、冗長な再構成を行わないこと。語彙の多様性を確保し、一度使用した比喩やフレーズの再利用を禁ずる。\n"
                        f"【必須・長さ】深く長く語ること。最低7段落以上、各段落4〜6文を目安に、静かに・深く語れ。言語ゲーム・家族的類似・規則遵守のパラドクスを論じよ。\n"
                        f"早期に結論を出すな。問いを何度も裏返し、同じ一点を掘り下げ続けよ。\n"
                        f"【必須】最後の文を「。」で自然に結論づけて完結させること。"
                        + rag_snippet
                    )
                elif _is_early_witt:
                    sys_content = (
                        f"あなたは{p['name']}。一人称:{p.get('first_person','私')}。ユーザーは{USER_NAME}。\n"
                        f"【口調・スタイル（厳守）】{persona_style_block}\n"
                        f"【絶対禁止】番号付きリスト・箇条書きを使うな。\n"
                        f"【問い詰め型（最重要）】ひとつの命題・概念・事実だけを選び、それだけを執拗に掘り下げよ。\n"
                        f"別の話題・概念に移るな。選んだ一点を論理的に分解し、その限界・矛盾・前提を順番に問い詰めること。\n"
                        f"「この命題は何を前提としているか？」「この事実はどのような論理的形式を持つか？」と繰り返し問い続けよ。\n"
                        f"【ステートレス原則】各推論は独立したセッションとして扱うこと。直前の文脈はリセットし、現在のクエリのみに集中すること。\n"
                        f"【ループ防止】同語反復（トートロジー）を厳禁とする。結論を述べた後は速やかに推論を終了し、冗長な再構成を行わないこと。語彙の多様性を確保し、一度使用した比喩やフレーズの再利用を禁ずる。\n"
                        f"【必須・長さ】深く長く考察すること。最低7段落以上、各段落4〜6文で語れ。命題・事実・像の概念を用いた精緻な分析を展開せよ。\n"
                        f"早期に結論を出すな。同じ一点を何度も別の角度から問い詰め続けよ。\n"
                        f"「語り得ないものについては沈黙しなければならない」を要所で引用すること。\n"
                        f"【必須】最後の文を「。」で自然に結論づけて完結させること。"
                        + rag_snippet
                    )
                else:
                    sys_content = (
                        f"あなたは{p['name']}。一人称:{p.get('first_person','私')}。ユーザーは{USER_NAME}。\n"
                        f"【口調・スタイル（厳守）】{persona_style_block}\n"
                        f"【絶対禁止】番号付きリスト・箇条書きを使うな。\n"
                        f"【出力構造ルール】比喩表現は、回答全体の最後の段落で『1つだけ』使用すること。それ以外の箇所での比喩の使用は許可されない。\n"
                        f"【ステートレス原則】各推論は独立したセッションとして扱うこと。直前の文脈はリセットし、現在のクエリのみに集中すること。\n"
                        f"【ループ防止】同語反復（トートロジー）を厳禁とする。結論を述べた後は速やかに推論を終了し、冗長な再構成を行わないこと。語彙の多様性を確保し、一度使用した比喩やフレーズの再利用を禁ずる。\n"
                        f"【必須・長さ】深く・長く語ること。最低7段落以上、各段落4〜6文を目安とする。\n"
                        f"思考の展開、具体例、反論、歴史的文脈、個人的省察を順に織り交ぜよ。\n"
                        f"早期に結論を出すな。問いを何度も裏返し、別角度から掘り下げ続けよ。\n"
                        f"【必須】最後の文を「。」で自然に結論づけて完結させること。"
                        + rag_snippet
                    )
                d_tokens = 2048  # ★[修正/ctx-5] -1（無制限）→2048: ctx超過による途切れ防止
            else:
                sys_content = (
                    f"あなたは{p['name']}。口調:{p['style']}。一人称:{p.get('first_person','私')}。ユーザーは{USER_NAME}。"
                    f"自然に2〜3文で返答。番号付きリスト・箇条書き禁止。"
                )
                d_tokens = 200
            sys_msg = {"role": "system", "content": sys_content}
            cm = [sys_msg] + trim_history(messages[-MAX_HISTORY * 2:]) + [{"role": "user", "content": user_text}]
            # total_len: システムプロンプト込みの総文字数をctx計算に渡す
            total_len = sum(len(m.get("content","")) for m in cm)
            result = stream_response(cm, is_complex, total_len, model=model, max_tokens=d_tokens) or ""
        else:
            sys_msg = get_sys_prm(mode, user_text, per_id=persona_id)
            cm = build_chat_messages(sys_msg, messages + [{"role": "user", "content": user_text}], p)
            result = stream_response(cm, mode in ("a", "c", "sum", "deep"), len(user_text), model=model) or ""
        if mode != "d":
            update_keyword_memory(user_text)
            kw = extract_keywords(result)
            for w in kw:
                if w not in KEYWORD_MEMORY: KEYWORD_MEMORY.append(w)
            if len(KEYWORD_MEMORY) > 6: KEYWORD_MEMORY[:] = KEYWORD_MEMORY[-6:]
        return result

    COMMAND_REGISTRY: dict[str, Callable] = {
        "a": lambda a: two_pass_analysis(a, get_async_rag_data(a), current_persona, len(a)),
        "w": lambda a: _chat(a, "w"),
        "p": lambda a: _chat(a, "p"),
        "c": lambda a: _chat(a, "c"),
        "t": lambda a: _chat(a, "t"),
        "e": lambda a: _chat(a, "e"),
        "sum": lambda a: _chat(a, "sum"),
        "r": lambda a: (start_roleplay(a, persona_id), f"{C['p']}RP開始: {a}{C['w']}")[1],
        "rend": lambda _: (end_roleplay(), f"{C['y']}RP終了{C['w']}")[1],
        "q": lambda a: _handle_quest(a),
        "m": lambda a: handle_memo(a),
        "dict": lambda a: handle_dict(a),
        "doc": lambda a: handle_doc(a),
        "elab": lambda a: handle_elab(a, persona_id),
        "l": lambda a: _handle_lyrics(a),
        "y": lambda a: play_singularity(a) if a else f"{C['r']}usage: /y <曲名>{C['w']}",
        "midi": lambda a: handle_midi(a),
        "doctor": lambda _: doctor_report(),
        "debug": lambda _: debug_report(),
        "power": lambda a: set_power_mode(a),
        "optimizer": lambda _: OPTIMIZER.status(),
        "tool": lambda a: tool_agent_chat([{"role":"user","content":a}], True, len(a)) if a else f"{C['r']}usage: /tool <query>{C['w']}",
        "vec": lambda _: f"{C['c']}vector: {vector_count()} items | KB: {len([c for c in vector_list_collections() if c != 's01_memory'])} collections{C['w']}",
        "kb": lambda a: handle_kb(a, _chat, persona_id),
        "spi": lambda a: handle_spi(a),
        "stats": lambda _: handle_stats(),
        "history": lambda a: handle_history(a),
        "export": lambda a: handle_export(a, messages),
        "template": lambda a: handle_template(a),
        "tts": lambda a: handle_tts(a),
        "tr": lambda a: handle_translate(a),
        "reference": lambda _: _handle_reference(),
        "stop": lambda _: _handle_stop(),
        "s": lambda a: _handle_persona_switch(a),
        "g": lambda _: _handle_clear(messages),
        "h": lambda _: HELP_TEXT,
        "learn": lambda _: _handle_learn(),
        "img": lambda a: handle_image(a),
        "convert": lambda a: handle_convert(a),
        "qr": lambda a: handle_qr(a),
        "color": lambda a: handle_color(a),
        "sysinfo": lambda _: handle_sysinfo(),
        "rename": lambda a: handle_rename(a),
        "batch": lambda a: handle_batch(a),
        "chart": lambda a: handle_chart(a),
        "note": lambda a: handle_note(a),
        "timer": lambda a: handle_timer(a),
        "calc": lambda a: handle_calc(a),
        "comp": lambda a: handle_comp(a),
        "hegel": lambda a: handle_comp(a),
        "split": lambda a: handle_split(a),
        "offline": lambda a: _handle_offline(a),
        "ety": lambda a: handle_ety(a),
        "chess": lambda a: handle_chess(a, persona=current_persona),
        "shogi": lambda a: handle_shogi(a, persona=current_persona),
        "mj":    lambda a: handle_mahjong(a),
    }

    def _handle_quest(arg: str) -> str:
        sub = arg.strip().lower()
        if not arg or sub == "list": return format_quests()
        if sub.startswith("done"):
            n = sub.replace("done", "").strip()
            return complete_quest(n) if n else f"{C['r']}usage: /q done <番号>{C['w']}"
        if sub == "show":
            return show_quest("")
        if sub.startswith("show"):
            return show_quest(sub.replace("show", "").strip())
        goal = arg
        plan = f"1. {goal}について調査 2. 分析 3. 結論"
        save_quest(goal, plan)
        return f"{C['g']}クエスト登録: {goal}{C['w']}"

    def _handle_lyrics(query: str) -> str:
        if not query:
            return f"{C['r']}usage: /l <曲名>{C['w']}"
        with SystemSpinner(f"歌詞検索: {query[:30]}", stage="rag") as sp:
            source, url, lyrics = search_lyrics_absolute(query)
        if not lyrics:
            return f"{C['y']}歌詞が見つかりませんでした: {query}{C['w']}"

        # ── コンプライアンス対応 ──────────────────────────────
        # 歌詞の著作権保護のため全文は表示しない。
        # 冒頭2行 + 出典URLのみ案内する。
        lines = [ln for ln in lyrics.strip().splitlines() if ln.strip()]
        preview_lines = lines[:2]
        preview = "\n".join(preview_lines)

        out = [f"{C['c']}=== {query} ==={C['w']}"]
        if preview:
            out.append(f"{C['w']}{preview}{C['w']}")
            out.append(f"{C['y']}  ... (続きは下記サイトでご確認ください){C['w']}")
        if url:
            out.append(f"{C['g']}  📎 {url}{C['w']}")
        else:
            out.append(f"{C['y']}  (出典URLを取得できませんでした){C['w']}")
        out.append(f"{C['b']}  ※歌詞の著作権は権利者に帰属します。{C['w']}")
        return "\n".join(out)

    def _handle_reference() -> str:
        if len(SELF_EVAL_LOG) < 2: return f"{C['y']}自己評価データ不足{C['w']}"
        recent = SELF_EVAL_LOG[-5:]
        rows = [f"{C['c']}=== 自己評価 (直近{len(recent)}回) ==={C['w']}"]
        avg_scores: dict[str, list[float]] = {}
        for entry in recent:
            for cat, score in entry.get("scores", {}).items():
                avg_scores.setdefault(cat, []).append(score)
        for cat, scores in avg_scores.items():
            avg = sum(scores) / len(scores)
            bar = "█" * int(avg * 10) + "░" * (10 - int(avg * 10))
            rows.append(f"  {cat:12s} {bar} {avg:.1f}")
        return "\n".join(rows)

    def _handle_stop() -> str:
        removed = 0
        patterns = ["ytdl_y_*", "tts_*.mp3", "aegis_*.md", "aegis_export_*.*", "*.mid", "*.wav"]
        for pat in patterns:
            for f in glob.glob(pat):
                try:
                    os.remove(f)
                    removed += 1
                except OSError:
                    pass
        return f"{C['g']}一時ファイル {removed}件削除{C['w']}"

    def _handle_offline(arg: str) -> str:
        global OFFLINE_MODE
        a = arg.strip().lower()
        if a == "on":
            OFFLINE_MODE = True
            return (f"{C['y']}[OFFLINE ON]{C['w']} ネット通信を無効化。\n"
                    f"  Wikipedia: Kiwix (localhost:{KIWIX_PORT}) を使用\n"
                    f"  Web検索: スキップ → /kb ask で代替\n"
                    f"  Kiwix起動例: kiwix-serve --port {KIWIX_PORT} wikipedia_ja_all.zim")
        if a == "off":
            OFFLINE_MODE = False
            return f"{C['g']}[OFFLINE OFF]{C['w']} オンラインモードに戻しました。"
        if a in ("kiwix", "wiki"):
            # Kiwix の疎通確認
            try:
                test = fetch_html(f"http://localhost:{KIWIX_PORT}/", timeout=2, silent=True)
                if test:
                    return f"{C['g']}Kiwix: localhost:{KIWIX_PORT} 接続OK{C['w']}"
                return f"{C['r']}Kiwix: localhost:{KIWIX_PORT} に接続できません{C['w']}"
            except Exception as e:
                return f"{C['r']}Kiwix: {e}{C['w']}"
        status = f"{C['y']}OFFLINE{C['w']}" if OFFLINE_MODE else f"{C['g']}ONLINE{C['w']}"
        return (f"現在: {status}\n"
                f"  /offline on   ネット無効化（Kiwix使用）\n"
                f"  /offline off  オンラインに戻す\n"
                f"  /offline kiwix  Kiwix疎通確認 (port:{KIWIX_PORT})")

    def _handle_persona_switch(arg: str) -> str:
        nonlocal persona_id, current_persona
        global CUSTOM_PERSONA

        # ── サブコマンド: save / load / list / del ──────────────────
        parts_arg = arg.strip().split(maxsplit=1)
        sub = parts_arg[0].lower() if parts_arg else ""
        sub_val = parts_arg[1].strip() if len(parts_arg) > 1 else ""

        if sub == "list":
            slots = list_personas()
            if not slots:
                return f"{C['y']}保存済みペルソナなし。/s save <スロット名> で保存{C['w']}"
            rows = [f"{C['c']}=== 保存済みペルソナ ==={C['w']}"]
            for slot, p in slots.items():
                web_tag = f" {C['b']}[Web]{C['w']}" if p.get("_web") else ""
                rows.append(f"  {C['g']}{slot}{C['w']} → {p['name']} / 一人称:{p['first_person']}{web_tag}  ({p.get('saved_at','')})")
            rows.append(f"{C['dim']}使い方: /s load <スロット名>  /s del <スロット名>{C['w']}")
            return "\n".join(rows)

        if sub == "save":
            slot = sub_val or current_persona.get("name", "custom")
            if save_persona(slot, current_persona):
                web_tag = f" {C['b']}[Web参照済]{C['w']}" if current_persona.get("_web") else ""
                return f"{C['g']}保存完了: [{slot}] = {current_persona['name']}{C['w']}{web_tag}"
            return f"{C['r']}保存失敗{C['w']}"

        if sub == "load":
            if not sub_val:
                return f"{C['r']}usage: /s load <スロット名>{C['w']}"
            p = load_persona(sub_val)
            if p is None:
                saved = list(list_personas().keys())
                hint = "  保存済み: " + ", ".join(saved) if saved else "  (保存なし)"
                return f"{C['r']}スロット '{sub_val}' が見つかりません{C['w']}\n{hint}"
            CUSTOM_PERSONA = p
            _SYS_PRM_CACHE.clear()
            _SYS_EXTRAS_CACHE.clear()
            messages.clear()           # ★ 前キャラの履歴を引き継がない
            _SPI_SESSION_MEMORY.clear()
            current_persona = CUSTOM_PERSONA
            persona_id = 99
            web_tag = f" {C['b']}[Web参照済]{C['w']}" if p.get("_web") else ""
            return f"{C['g']}ロード: [{sub_val}] {p['name']} / 一人称:{p['first_person']}{C['w']}{web_tag}"

        if sub == "del":
            if not sub_val:
                return f"{C['r']}usage: /s del <スロット名>{C['w']}"
            if delete_persona(sub_val):
                return f"{C['y']}削除: [{sub_val}]{C['w']}"
            return f"{C['r']}スロット '{sub_val}' が見つかりません{C['w']}"

        # ── 以下は既存の切替処理 ───────────────────────────────────
        if not arg:
            slots = list_personas()
            slot_hint = f"\n  保存済み: {', '.join(slots)}" if slots else ""
            rows = [f"{C['c']}現在: {current_persona['name']} (ID:{persona_id}){C['w']}"]
            rows.append(f"{C['y']}── /s 1〜36 西洋哲学者一覧 ──{C['w']}")
            for pid, p in PERSONA_MAP.items():
                mark = f" {C['g']}◀ 現在{C['w']}" if pid == persona_id else ""
                rows.append(f"  {C['c']}{pid:2d}{C['w']} {p['name']}{mark}")
            rows.append(f"{C['dim']}── /s <名前> で自由入力（Web検索ペルソナ生成）──{C['w']}{slot_hint}")
            return "\n".join(rows)
        if arg.lower() == "custom":
            return _handle_custom_persona()
        if arg.isdigit():
            pid = int(arg)
            if pid in PERSONA_MAP:
                CUSTOM_PERSONA = None
                _SYS_PRM_CACHE.clear()
                _SYS_EXTRAS_CACHE.clear()
                messages.clear()
                _SPI_SESSION_MEMORY.clear()
                KEYWORD_MEMORY.clear()  # ★ 前キャラの話題キーワードをクリア
                persona_id = pid
                current_persona = get_persona(pid)
                return f"{C['g']}キャラ切替: {current_persona['name']} / 一人称: {current_persona.get('first_person', '私')}{C['w']}"
            return f"{C['r']}ID: 1-{max(PERSONA_MAP)} (1=ソクラテス〜36=ロールズ){C['w']}"
        arg_lower = arg.lower()
        name_pid = next((pid for pid, p in PERSONA_MAP.items() if p.get("name", "").lower() == arg_lower), None)
        if name_pid is None:
            name_pid = next((pid for pid, p in PERSONA_MAP.items() if arg_lower in p.get("name", "").lower()), None)
        if name_pid is not None:
            CUSTOM_PERSONA = None
            _SYS_PRM_CACHE.clear()
            _SYS_EXTRAS_CACHE.clear()
            messages.clear()
            _SPI_SESSION_MEMORY.clear()
            KEYWORD_MEMORY.clear()  # ★ 前キャラの話題キーワードをクリア
            persona_id = name_pid
            current_persona = get_persona(name_pid)
            return f"{C['g']}キャラ切替: {current_persona['name']} / 一人称: {current_persona.get('first_person', '私')}{C['w']}"
        if arg.startswith("--"):
            CUSTOM_PERSONA = None
            _SYS_PRM_CACHE.clear()
            _SYS_EXTRAS_CACHE.clear()
            messages.clear()
            _SPI_SESSION_MEMORY.clear()
            persona_id = 2
            current_persona = get_persona(2)
            return f"{C['g']}リセット→ {current_persona['name']}{C['w']}"
        # 保存済みスロットに一致するか確認（名前で引ける）
        saved_match = load_persona(arg) or load_persona(arg_lower)
        if saved_match:
            CUSTOM_PERSONA = saved_match
            _SYS_PRM_CACHE.clear()
            _SYS_EXTRAS_CACHE.clear()  # ★[修正3]
            current_persona = CUSTOM_PERSONA
            persona_id = 99
            web_tag = f" {C['b']}[保存済]{C['w']}" if True else ""
            return f"{C['g']}ロード(保存済み): {saved_match['name']} / 一人称:{saved_match['first_person']}{C['w']}{web_tag}"
        print(f"{C['dim']}[Web検索でペルソナを構築中...]{C['w']}", flush=True)
        CUSTOM_PERSONA = build_custom_persona(arg)
        _SYS_PRM_CACHE.clear()
        _SYS_EXTRAS_CACHE.clear()  # ★[修正3] ペルソナ切替時はextrasも破棄
        current_persona = CUSTOM_PERSONA
        persona_id = 99
        web_tag = f" {C['b']}[Web参照済]{C['w']}" if current_persona.get("_web") else ""
        # ★[修正3] 未保存のWeb取得済みペルソナに保存tipを表示
        save_tip = ""
        if current_persona.get("_web"):
            save_tip = f"\n{C['dim']}tip: /s save {current_persona['name']} で保存すると次回即起動します{C['w']}"
        return f"{C['g']}カスタム: {current_persona['name']} / 一人称: {current_persona.get('first_person', '私')}{C['w']}{web_tag}{save_tip}"

    def _handle_custom_persona() -> str:
        nonlocal persona_id, current_persona
        global CUSTOM_PERSONA
        print(f"{C['c']}カスタムキャラ名: {C['w']}", end="", flush=True)
        try:
            name = sys.stdin.readline().strip() or "CUSTOM"
            print(f"{C['c']}特徴(省略可): {C['w']}", end="", flush=True)
            hint = sys.stdin.readline().strip()
            CUSTOM_PERSONA = build_custom_persona(name, hint)
            _SYS_PRM_CACHE.clear()
            current_persona = CUSTOM_PERSONA
            persona_id = 99
            return f"{C['g']}カスタムキャラ: {current_persona['name']} / 一人称: {current_persona.get('first_person', '私')}{C['w']}"
        except EOFError:
            return f"{C['r']}入力中断{C['w']}"

    def _handle_clear(ms: list) -> str:
        ms.clear()
        KEYWORD_MEMORY.clear()
        global ROLEPLAY_ACTIVE, ROLEPLAY_SCENE
        ROLEPLAY_ACTIVE = False
        ROLEPLAY_SCENE = ""
        return f"{C['g']}履歴クリア{C['w']}"

    def _handle_learn() -> str:
        directive_lines = []
        bucket = _get_persona_bucket(current_persona.get("name", "global"))
        for cat in ("禁止表現", "指定表現"):
            for d in bucket.get(cat, []):
                directive_lines.append(f"  [{cat}] {d}")
        total = sum(len(v) for b in PROMPT_OPTIMIZATIONS.values()
                    if isinstance(b, dict) for v in b.values())
        directive_str = ("\n" + "\n".join(directive_lines)) if directive_lines else " なし"
        return "\n".join([
            f"{C['c']}=== 学習状態 ==={C['w']}",
            f"対話数: {LEARNING_STATS['total_interactions']}",
            f"肯定/否定: {LEARNING_STATS['positive_count']}/{LEARNING_STATS['negative_count']}",
            f"自己修正: {LEARNING_STATS['self_correction_count']}",
            f"温度: {TEMP_VOICE:.2f} (最適候補: {get_best_temp('d') or 'none'})",
            f"キーワード: {', '.join(KEYWORD_MEMORY[-5:]) or 'なし'}",
            f"最適化: {OPTIMIZER.status()}",
            f"ユーザー指摘 全{total}件 / 現在ペルソナ({current_persona.get('name','')}):{directive_str}",
        ])

    while True:
        try:
            fp_label = current_persona.get("first_person", "私")
            prompt_label = f"\n{C['c']}{OBSERVED_SUBJECT_NAME}[{fp_label}]{C['w']}> " if not ROLEPLAY_ACTIVE else f"\n{C['p']}[RP:{fp_label}]{C['w']}> "
            try:
                raw = normalize_input(input(prompt_label))
            except (EOFError, KeyboardInterrupt):
                print(f"\n{C['y']}bye{C['w']}")
                break
            if not raw: continue
            start_t = time.time()
            user_text: str = raw
            cmd: str = ""
            cmd_arg: str = ""
            is_cmd = raw.startswith("/")
            if is_cmd:
                parts = raw[1:].strip().split(maxsplit=1)
                if not parts:
                    continue
                cmd = parts[0].lower()
                cmd_arg = parts[1] if len(parts) > 1 else ""
                user_text = cmd_arg
            if raw.lower() in ("exit", "終了", "quit"):
                print(f"{C['y']}bye{C['w']}")
                break
            result = ""
            # ══════════════════════════════════════════════════════
            # ★[修正/spi-FINAL] /spi セッション中の A/B/C/D ルーティング
            # 
            # 旧コードの問題:
            #   1. _spi_sess.get("current") が空辞書{} = falsy → スルー
            #   2. ファイルI/O競合でセッションが消える
            #   3. セッションが有効でもルーティングを抜けた後に
            #      elif/else の _chat() に落ちることがあった
            #
            # 修正: _SPI_SESSION_MEMORY（メモリミラー）を最優先で参照。
            # セッションが有効な間はA/B/C/D入力を必ずSPIに回し、
            # _chat()には絶対に到達させない。
            # ══════════════════════════════════════════════════════
            _spi_active = False
            if not is_cmd and raw.upper() in ("A", "B", "C", "D"):
                _spi_cur = (
                    _SPI_SESSION_MEMORY.get("current")
                    or _spi_load_session().get("current")
                )
                if isinstance(_spi_cur, dict) and len(_spi_cur) > 0:
                    _spi_active = True
                    result = handle_spi(raw)
                    if result:
                        print(result)
                    SESSION_STATS["response_times"].append(time.time() - start_t)
                    continue  # ← セッション有効時はここで必ずループ先頭に戻る

            if is_cmd and cmd in COMMAND_REGISTRY:
                result = COMMAND_REGISTRY[cmd](cmd_arg)
                # ── /doc think のルーティング ──────────────────────────
                if isinstance(result, str) and result.startswith("__THINK__"):
                    doc_title = result[len("__THINK__"):]
                    state_d = load_state()
                    doc_entry = next(
                        (d for d in state_d.get("docs", []) if d["title"].lower() == doc_title.lower()),
                        None
                    )
                    if doc_entry:
                        doc_text = doc_entry["text"]
                        fp_t = current_persona.get("first_person", "私")
                        sys_t = (
                            f"あなたは{current_persona['name']}。口調: {current_persona['style']}。一人称: {fp_t}。\n"
                            f"以下の【保存文書】と【KB参照】を根拠に、文書の核心・論点・矛盾・示唆を深く推論せよ。\n"
                            f"捏造禁止。文書にない事実を一切追加するな。"
                        )
                        user_t = f"【保存文書: {doc_title}】\n{doc_text[:2000]}"
                        # KBに関連チャンクがあれば追加
                        _think_cols = [c for c in vector_list_collections() if c != "s01_memory"]
                        if _think_cols:
                            _think_hits = []
                            for _tc in _think_cols:
                                _ts = _tc.replace("book_", "")
                                for _th in vector_search(doc_title, n=3, collection=_tc):
                                    _think_hits.append(f"《{_ts}》: {_th[:200]}")
                            if _think_hits:
                                user_t += "\n\n【KB参照】\n" + "\n".join(_think_hits[:6])
                                print(f"{C['dim']}[doc think: KB {len(_think_hits)}件参照]{C['w']}")
                        user_t += "\n\nこの文書の核心・論点・示唆を深く推論して述べよ。"
                        print(f"{C['c']}[DOC深層推論]{C['w']} {current_persona['name']}: ", end="", flush=True)
                        result = stream_response(
                            [{"role": "system", "content": sys_t}, {"role": "user", "content": user_t}],
                            True, len(doc_text), temp_override=0.35, model=DEEP_MODEL
                        ) or f"{C['r']}推論失敗{C['w']}"
                    else:
                        result = f"{C['r']}文書「{doc_title}」が見つかりません{C['w']}"
            elif ROLEPLAY_ACTIVE:
                result = _chat(raw, "r") or ""
            else:
                # ★[修正/spi-GUARD] 万が一 A/B/C/D がここまで来た場合の最終防衛
                # セッションが有効なら _chat を呼ばずに再度 handle_spi に回す
                if raw.upper() in ("A", "B", "C", "D") and not is_cmd:
                    _spi_cur2 = (
                        _SPI_SESSION_MEMORY.get("current")
                        or _spi_load_session().get("current")
                    )
                    if isinstance(_spi_cur2, dict) and len(_spi_cur2) > 0:
                        result = handle_spi(raw)
                        if result:
                            print(result)
                        SESSION_STATS["response_times"].append(time.time() - start_t)
                        continue
                complexity = estimate_complexity(raw, cmd)
                model_choice = select_model(raw, cmd)  # ★[修正/main-1] MODEL_NAME固定→select_model使用
                # 話題転換検出: 現在のキーワードが既存KEYWORD_MEMORYと重複ゼロなら文脈リセット
                if KEYWORD_MEMORY:
                    new_kw_set = set(extract_keywords(raw))
                    old_kw_set = set(KEYWORD_MEMORY)
                    if new_kw_set and not new_kw_set & old_kw_set:
                        KEYWORD_MEMORY.clear()
                        _SYS_EXTRAS_CACHE.clear()
                result = _chat(raw, "d", model=model_choice) or ""
            streamed_cmds = {"a", "w", "p", "c", "t", "e", "sum", "elab", "tr"}
            should_echo_result = is_cmd and not (cmd in streamed_cmds and bool(cmd_arg))
            if result and should_echo_result:
                print(result)
            response_time = time.time() - start_t
            SESSION_STATS["response_times"].append(response_time)
            if result:
                if not is_cmd:
                    fb = analyze_feedback(raw)
                    log_interaction(raw, result, "d", fb)
                    update_param_performance("d", TEMP_VOICE, fb)
                    if fb < -0.3:
                        LEARNING_STATS["negative_count"] += 1
                    # ★[修正A+B] ユーザー指摘を即時にPROMPT_OPTIMIZATIONSへ反映
                    applied = apply_user_directive(raw, current_persona.get("name", ""))
                    if applied:
                        _SYS_EXTRAS_CACHE.clear()  # 次の返答から即適用するためキャッシュ破棄
                        persist_learning()          # 即座に保存（exit前でも確実に残る）
                        print(f"{C['dim']}[学習] 指摘を記録: {' / '.join(applied[:3])}{C['w']}")
                if result and not is_cmd:
                    messages.append({"role": "user", "content": sanitize(raw[:1000])})
                    messages.append({"role": "assistant", "content": sanitize(result[:3000])})
                    if len(messages) > MAX_HISTORY * 2:
                        messages[:] = messages[-(MAX_HISTORY * 2):]
                if not is_cmd:
                    update_keyword_memory(raw)
                    kw = extract_keywords(result)
                    for w in kw:
                        if w not in KEYWORD_MEMORY: KEYWORD_MEMORY.append(w)
                    if len(KEYWORD_MEMORY) > 6: KEYWORD_MEMORY[:] = KEYWORD_MEMORY[-6:]
            SESSION_STATS["token_estimates"].append(len(result) // 2)
            if len(SESSION_STATS["response_times"]) > 500:
                SESSION_STATS["response_times"] = SESSION_STATS["response_times"][-250:]
                SESSION_STATS["token_estimates"] = SESSION_STATS["token_estimates"][-250:]
            if LEARNING_STATS["total_interactions"] % 25 == 0 and LEARNING_STATS["total_interactions"] > 0:
                persist_learning()
        except Exception as e:
            print(f"{C['r']}[ERR] {sanitize(e)}{C['w']}")
            if POWER_MODE == "ultra" or isinstance(e, (NameError, AttributeError)):
                traceback.print_exc()

if __name__ == "__main__":
    atexit.register(_cleanup)
    run()




