#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# s01_handlers.py — 各種コマンドハンドラ群 (memo/dict/doc/quest/image/chart/comp/split…)
from __future__ import annotations
from s01_config import *
from s01_config import _get_ollama, _get_or_create_col, _init_vector_db, _exec_tool, _reg_tool, _persona_key, _get_persona_bucket
from s01_rag import stream_response, fetch_html, get_async_rag_data
from s01_persona import get_persona, save_persona, load_persona, delete_persona, list_personas
from s01_learning import SELF_EVAL_LOG

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
        except Exception:
            pass

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
                # ★ 追加哲学者
                "ベーコン": "bacon", "パスカル": "pascal", "ルソー": "rousseau",
                "ヴォルテール": "voltaire", "マキャベリ": "machiavelli",
                "フロイト": "freud", "ユング": "jung", "フーコー": "foucault",
                "アレント": "arendt", "レヴィ＝ストロース": "levi-strauss",
                "デリダ": "derrida", "ロールズ": "rawls",
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
        except Exception:
            pass
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
        except Exception:
            pass

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
    if not os.path.exists(old): return f"{C['r']}ファイルなし: {old}{C['w']}"
    try: os.rename(old, new); return f"{C['g']}リネーム: {old} → {new}{C['w']}"
    except Exception as e: return f"{C['r']}error: {e}{C['w']}"

def handle_batch(arg: str) -> str:
    parts = arg.split(None, 1)
    if len(parts) < 2: return f"{C['r']}usage: /batch <cmd> <path>  例: /batch count .{C['w']}"
    cmd, path = parts[0].lower(), parts[1].strip()
    if not os.path.exists(path): return f"{C['r']}パスなし: {path}{C['w']}"
    if cmd == "count":
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8", errors="ignore") as f: data = f.read()
            return f"{C['g']}行数: {data.count(chr(10))+1}, 文字数: {len(data)}{C['w']}"
        else:
            files = [f for f in os.listdir(path) if os.path.isfile(os.path.join(path, f))]
            return f"{C['g']}ファイル数: {len(files)}{C['w']}"
    elif cmd == "size":
        if os.path.isfile(path): return f"{C['g']}サイズ: {os.path.getsize(path)} bytes{C['w']}"
        total = sum(os.path.getsize(os.path.join(path, f)) for f in os.listdir(path) if os.path.isfile(os.path.join(path, f)))
        return f"{C['g']}合計サイズ: {total//1024}KB{C['w']}"
    elif cmd == "list":
        if os.path.isdir(path):
            items = os.listdir(path)
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
    allowed = set("0123456789+-*/.()%eE piPsqrlcosinta,=<>")
    if any(c not in allowed for c in expr): return f"{C['r']}許可されていない文字{C['w']}"
    try:
        ns = {"__builtins__": {}, "math": math}
        # Handle common patterns
        expr = expr.replace("^", "**").replace("×", "*").replace("÷", "/")
        result = eval(expr, ns)
        return f"{C['g']}= {result}{C['w']}"
    except Exception as e: return f"{C['r']}error: {e}{C['w']}"

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
    p1 = get_persona(int(id1)) if id1.isdigit() and 1 <= int(id1) <= max(PERSONA_MAP) else {"name": id1, "style": f"{id1}の口調で話す", "first_person": "私"}
    p2 = get_persona(int(id2)) if id2.isdigit() and 1 <= int(id2) <= max(PERSONA_MAP) else {"name": id2, "style": f"{id2}の口調で話す", "first_person": "私"}

    # ★[修正/comp-2] モード判定: 哲学者(1-N)同士 → 哲学的対話モードを新設
    PHILOSOPHER_IDS = set(range(1, max(PERSONA_MAP) + 1))
    BUSINESS_KW = {"社長", "部長", "課長", "教授", "博士", "先生", "CEO", "CTO", "役員", "責任者", "マネージャ", "マネージャー", "リーダー", "秘書", "S-01", "執事", "医師", "秀才", "エンジニア", "管理職", "弁護士", "会計士", "コンサル", "アナリスト", "ディレクター", "プロデューサー"}
    CASUAL_NAME_KW = {"お嬢様", "おじょうさま", "ギャル", "ツンデレ", "クール", "無口", "元気", "子供", "魔王", "勇者", "魔法使い", "忍者", "侍", "ヤンキー", "天然", "腹黒", "中二病", "猫", "犬", "恋人", "友達", "彼女", "彼氏", "妹", "姉", "弟", "兄", "ママ", "パパ"}
    CASUAL_PERSONA_IDS = set(range(1, max(PERSONA_MAP) + 1))  # 哲学者全員をcasual判定から除外し、philosopher優先
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
    base = (get_persona(int(id1)) if id1.isdigit() and 1 <= int(id1) <= max(PERSONA_MAP)
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
    except Exception:
        pass

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
