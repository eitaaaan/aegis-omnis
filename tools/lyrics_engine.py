# -*- coding: utf-8 -*-
import urllib.parse as U
import urllib.request as R
import re, html, ssl, unicodedata, threading

def fetch_html(url):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    headers = {"User-Agent": "Mozilla/5.0", "Accept-Language": "ja,en;q=0.9"}
    try:
        req = R.Request(url, headers=headers)
        with R.urlopen(req, context=ctx, timeout=5) as resp:
            raw = resp.read()
            return raw.decode("utf-8", "ignore")
    except: return ""

def search_lyrics(query):
    """Yahoo検索経由で歌ネット等の歌詞ページを探し、中身を抽出する"""
    search_url = f"https://search.yahoo.co.jp/search?p={U.quote(query + ' 歌詞')}"
    html_content = fetch_html(search_url)
    
    # 歌ネット(uta-net)のURLを探す
    match = re.search(r'https://www.uta-net.com/song/\d+/', html_content)
    if not match: return None, None
    
    target_url = match.group(0)
    page_html = fetch_html(target_url)
    
    # タイトルと歌詞本文を抽出
    title_m = re.search(r'<h2[^>]*>(.*?)</h2>', page_html, re.S)
    body_m = re.search(r'<div id="kashi_area"[^>]*>(.*?)</div>', page_html, re.S)
    
    if title_m and body_m:
        title = re.sub(r'<[^>]+>', '', title_m.group(1)).strip()
        # <br>を改行に変換し、他のタグを消す
        lyrics = body_m.group(1).replace('<br />', '\n').replace('<br>', '\n')
        lyrics = re.sub(r'<[^>]+>', '', lyrics).strip()
        return title, lyrics
    
    return None, None