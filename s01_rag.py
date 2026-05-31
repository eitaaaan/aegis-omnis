#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# s01_rag.py — HTTP取得・RAG・Web検索(Brave/Yahoo/Bing/DDG/NHK)
from __future__ import annotations
from s01_config import *
from s01_persona import *

def fetch_html(url: str, data: bytes | None = None, timeout: int = 5, silent: bool = False, spoof_bot: bool = False) -> str:
    import random
    ua = random.choice(["Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/605.1.15"])
    headers = {"User-Agent": ua, "Accept-Language": "ja,en;q=0.9", "Accept": "text/html,*/*;q=0.8"}
    if spoof_bot: headers["Referer"] = "https://www.google.co.jp/"
    try:
        req = R.Request(url, data=data, headers=headers)
        with _opener.open(req, timeout=timeout) as resp:
            raw = resp.read()
            for enc in ("utf-8", "shift_jis", "euc-jp"):
                try: return raw.decode(enc)
                except UnicodeDecodeError: continue
            return raw.decode("utf-8", "ignore")
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
            except Exception:
                pass
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
    except Exception:
        pass
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
            if sum(len(res.get(k, "")) for k in ["yahoo", "ddg", "bing", "kotobank"]) > 600: break
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
            oldest = sorted(RAG_CACHE.items(), key=lambda x: x[1][0])[:20]
            for k, _ in oldest: RAG_CACHE.pop(k, None)
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
    with SystemSpinner("RAG事実抽出中...", stage="pass1") as sp1:
        lines_rag = [re.sub(r'[^\x20-\x7E\u3000-\u9FFF\uFF00-\uFFEF]', '', ln.strip()) for ln in rag_data.splitlines()]
        lines_rag = [ln for ln in lines_rag if len(ln) >= FACT_MIN_CHARS and ln not in ("(empty)", "")]
        q_words = [w for w in re.split(r'[\s\u3000\u3001\u3002\uff0c\uff0e]+', query) if len(w) >= 2]
        scored = sorted([(sum(1 for w in q_words if w in ln) + len(ln) * 0.001, ln) for ln in lines_rag], key=lambda x: -x[0])
        facts = [ln[:200] for _, ln in scored[:8]]
        raw_p1 = "\n".join(f"<FACT>[HIGH] {f}</FACT>" for f in facts[:4]) + "\n".join(f"<FACT>[MID] {f}</FACT>" for f in facts[4:])
    elapsed1 = sp1._elapsed
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

    # _is_sentence_complete は継続生成廃止に伴い削除済み

def _find_overlap(base: str, continuation: str, max_check: int = 80) -> int:
    """base の末尾と continuation の先頭の重複長を返す。重複除去に使用。"""
    tail = base[-max_check:]
    for length in range(min(max_check, len(continuation)), 0, -1):
        if tail.endswith(continuation[:length]):
            return length
    return 0

def _single_gen(o, model: str, msgs: list, opts: dict, silent: bool, timeout: int) -> tuple:
    """1回分の生成。タイムアウトなしの直接ストリーミング。(テキスト, 成功フラグ) を返す。"""
    # ★ スレッド+タイムアウト方式を廃止。
    # th.join(timeout=N) が N秒で部分テキストを返すのが途切れの根本原因だった。
    # Ollamaのストリームを直接イテレートし、モデルが止まるまで待ち続ける。
    try:
        full = ""
        for chunk in o.chat(model=model, messages=msgs, stream=True, options=opts, keep_alive=-1):
            msg = chunk.get("message", {}) if isinstance(chunk, dict) else getattr(chunk, "message", None)
            if isinstance(msg, dict): t = msg.get("content", "")
            else: t = getattr(msg, "content", "")
            if not isinstance(t, str) or not t: continue
            t = sanitize(t)
            if not t: continue
            if not silent: print(t, end="", flush=True)
            full += t
        return full, True
    except KeyboardInterrupt:
        # Ctrl+C で中断された場合は途中テキストを返す
        return full if 'full' in dir() else "", False
    except Exception as e:
        if not silent: print(f"\n{C['r']}[ERR] {e}{C['w']}")
        return "", False


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
    opts = get_llm_opt(is_logic, text_len, temp_override, max_tokens=max_tokens)

    full_result, ok = _single_gen(o, model, messages, opts, silent, 0)
    if not full_result.strip():
        if not silent: print(f"\n{C['r']}[ERR] 応答がありません{C['w']}")
        return ""

    # 繰り返しループ検出 → 末尾を整形して返す
    if detect_repetition(full_result):
        t = full_result.rstrip("、，")
        TERMINAL = {"。", "．", "！", "？", "…", "」", "』", "】", "）", ")", ".", "!", "?"}
        if t and t[-1] not in TERMINAL:
            full_result = t + "。"
        else:
            full_result = t

    if not silent: print()
    return full_result

def get_llm_opt(is_logic_mode: bool, text_len: int = 0, temp_override: float | None = None, max_tokens: int | None = None) -> dict:
    power = POWER_MODE
    configs = {
        "ultra": (12288, 4096, 4096, 0.12, 0.74, 8),
        "high":  (8192,  2048, 2000, 0.18, 0.78, 8),
        "mid":   (4096,  2000, 1600, 0.18, 0.78, 6),  # 1200→1600: 1発完結のため
        "low":   (2048,   700,  600, 0.20, 0.78, 4),
    }
    ctx, pl, pc, tl, tc, threads = configs.get(power, configs["high"])
    if is_logic_mode:
        # complexモード: text_lenに依存せずctx・num_predictを固定最大化
        ctx = 8192
        num_predict = 4096
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
    if actual_predict == -1 or actual_predict is None:
        actual_predict = 4096
    else:
        actual_predict = max(1, int(actual_predict))
    if is_logic_mode:
        return dict(num_ctx=ctx, num_predict=actual_predict, temperature=final_temp, top_k=30, top_p=0.86,
                    repeat_penalty=1.25,  # ★ 繰り返し比喩ループ防止
                    repeat_last_n=128,
                    num_thread=threads, num_batch=512, stop=stop_words)
    return dict(num_ctx=ctx, num_predict=actual_predict, temperature=final_temp, top_k=20, top_p=0.85,
                repeat_penalty=1.20,  # ★ 旧1.05→1.20: 「それはまるで〜」ループ防止
                repeat_last_n=128,
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

def normalize_for_match(text: str) -> str:
    text = html_module.unescape(text or "")
    text = re.sub(r"<[^>]+>", "", text)
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"[!-/:-@\[-`{-~\u3001\u3002\u30fb\u2026\u301c\uff01\uff1f\u300c-\u300f\u3010\u3011・…～―\s]", "", text)
    return text.lower()

def is_url(text: str) -> bool: return text.startswith("http://") or text.startswith("https://")

