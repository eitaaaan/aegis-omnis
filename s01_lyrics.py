#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# s01_lyrics.py — 歌詞検索エンジン
from __future__ import annotations
from s01_config import *
from s01_rag import fetch_html, strip_tags

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

