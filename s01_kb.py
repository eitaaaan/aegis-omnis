#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# s01_kb.py — ローカルRAG・ファイル取り込み・オフライン推論
from __future__ import annotations
from s01_config import *
from s01_rag import stream_response, fetch_html
from s01_config import VECTOR_COL, vector_add, vector_search, vector_count, vector_list_collections, _get_or_create_col

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
                    f"  {ok}/{len(chunks)} チャンク → コレクション「{_slug}」{C['w']}")

        # ── ファイルパス ──────────────────────────────────────────
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
                f"  {ok}/{len(chunks)} \u30c1\u30e3\u30f3\u30af \u2192 \u30b3\u30ec\u30af\u30b7\u30e7\u30f3\u300c{col_name.replace('book_','')}\u300d{C['w']}")

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
