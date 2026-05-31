# -*- coding: utf-8 -*-
import urllib.parse as U
import urllib.request as R
import re
import html as html_module
import ssl
import json
from http.cookiejar import CookieJar

_ctx = ssl.create_default_context()
_ctx.check_hostname = False
_ctx.verify_mode = ssl.CERT_NONE
_opener = R.build_opener(R.HTTPSHandler(context=_ctx), R.HTTPCookieProcessor(CookieJar()))

def fetch_html(url: str, data: bytes | None = None, timeout: int = 8, silent: bool = False, spoof_bot: bool = False) -> str:
    headers = {"User-Agent": "Mozilla/5.0", "Accept-Language": "ja,en;q=0.9", "DNT": "1"}
    if spoof_bot: headers["Referer"] = "https://www.google.co.jp/"
    try:
        with _opener.open(R.Request(url, data=data, headers=headers), timeout=timeout) as resp:
            raw = resp.read()
            for enc in ("utf-8", "shift_jis", "euc-jp"):
                try: return raw.decode(enc)
                except UnicodeDecodeError: continue
            return raw.decode("utf-8", "ignore")
    except Exception as e:
        if not silent: print(f"[NET ERR] {e}")
        return ""

def strip_tags(fragment: str) -> str: 
    return html_module.unescape(re.sub(r"<[^>]+>", "", re.sub(r"(?i)<br\s*/?>", "\n", fragment))).strip()

def sanitize(txt: str) -> str: 
    return re.sub(r'[\ud800-\udfff]', '', str(txt)).encode("utf-8", "ignore").decode("utf-8")

def fetch_bing_snippets(query: str) -> str:
    url = "https://www.bing.com/search?q=" + U.quote(query) + "&setlang=ja&cc=JP&mkt=ja-JP"
    h = fetch_html(url, timeout=6, silent=True, spoof_bot=True)
    snips = re.findall(r'<div class="b_caption">.*?<p[^>]*>(.*?)</p>', h, re.I | re.S) or re.findall(r'<p class="b_paractl"[^>]*>(.*?)</p>', h, re.I | re.S)
    return sanitize("\n".join(strip_tags(s) for s in snips[:4]))

def fetch_ddg_snippets(query: str) -> str:
    data = U.urlencode({"q": query, "kl": "jp-jp"}).encode("utf-8")
    h = fetch_html("https://lite.duckduckgo.com/lite/", data=data, timeout=6, silent=True)
    snips = re.findall(r'class="result-snippet"[^>]*>(.*?)</td>', h, re.I | re.S)
    return sanitize("\n".join(strip_tags(s) for s in snips[:4]))

def fetch_subculture(query: str) -> str:
    sub_query = f"{query} (site:fandom.com OR site:w.atwiki.jp)"
    return fetch_ddg_snippets(sub_query)

def get_wikipedia(query: str) -> str:
    url = "https://ja.wikipedia.org/w/api.php?format=json&action=query&prop=extracts&explaintext&redirects=1&titles=" + U.quote(query)
    raw = fetch_html(url, timeout=8, silent=True)
    if raw:
        for pid, page in json.loads(raw).get("query", {}).get("pages", {}).items():
            if pid != "-1" and page.get("extract"): return sanitize(page["extract"][:2000])
    return ""