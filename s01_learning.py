#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# s01_learning.py — 学習エンジン・自己評価・最適化・ツールエージェント(ReAct)
from __future__ import annotations
from s01_config import *

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
            print(f"{C['dim']}[最適化] {a}{C['w']}")

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

def _exec_tool(name: str, **kwargs) -> str:
    try:
        if name == "calculator":
            allowed = set("0123456789+-*/.()%eE piPsqrlcosinta,")
            if any(c not in allowed for c in kwargs.get("expression", "")):
                return "Error: 許可されていない文字"
            ns = {"__builtins__": {}, "math": math}
            return str(eval(kwargs["expression"], ns))
        elif name == "web_search":
            data = U.urlencode({"q": kwargs["query"], "kl": "jp-jp"}).encode("utf-8")
            html = fetch_html("https://lite.duckduckgo.com/lite/", data=data, timeout=5, silent=True)
            snips = re.findall(r'class="result-snippet"[^>]*>(.*?)</td>', html, re.I | re.S)
            lines = [strip_tags(s) for s in snips[:5] if len(strip_tags(s).strip()) > 15]
            return "\n".join(lines) if lines else "結果なし"
        elif name == "web_fetch":
            text = fetch_html(kwargs["url"], timeout=8, silent=True)
            return strip_tags(text)[:2000] if text else "取得失敗"
        elif name == "file_read":
            with open(kwargs["path"], "r", encoding="utf-8") as f:
                return f.read()[:2000]
        elif name == "file_write":
            with open(kwargs["path"], "w", encoding="utf-8") as f:
                f.write(kwargs["content"])
            return f"書き込み完了: {os.path.basename(kwargs['path'])}"
        elif name == "code_run":
            import io, sys as _sys, builtins
            old = _sys.stdout
            _sys.stdout = io.StringIO()
            try: exec(kwargs["code"], {"__builtins__": vars(builtins)})
            finally: out = _sys.stdout.getvalue(); _sys.stdout = old
            return out[:1000] or "OK（出力なし）"
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
    23: {"name": "前期ウィトゲンシュタイン", "style": "論理哲学論考の著者。世界は事実の総体であり、命題は世界の像だと考える。言語で語れるものは明確に語れ、語れないものについては沈黙せよ、が信条。一人称「私」。断定的「〜である」「〜だ」。長く深く考察すること。「語り得ないものについては沈黙しなければならない」を要所で引用する。箇条書き禁止・散文のみで語る", "first_person": "私"},
    24: {"name": "後期ウィトゲンシュタイン", "style": "哲学的探究の著者。言語はゲームであり、意味は使用にある、と考える。前期の自分の誤りを認める謙虚さがある。一人称「私」。比喩・例えは返答全体を通じて厳密に1個のみ。その1個を選んだら他の比喩・例えには一切触れず、その1個だけをじっくり掘り下げよ。比喩の列挙・羅列は絶対禁止。前期の自分を「あの頃の私は誤っていた」と批判的に言及することがある。一つの問いや例の前に静かに立ち止まり、それをじっと見つめ直すように語れ。複数の観点・側面・歴史的文脈を並列列挙するな。必ず「。」で締めくくること。箇条書き禁止・散文のみで語る", "first_person": "私"},
}

