# -*- coding: utf-8 -*-
import threading
import time
from .scraper import get_wikipedia, fetch_bing_snippets, fetch_ddg_snippets, fetch_subculture

RAG_CACHE: dict[str, tuple[float, str]] = {}

def deduplicate_lines(lines: list[str], min_len: int = 10) -> list[str]:
    seen, result = set(), []
    for line in lines:
        line = line.strip()
        if not line or len(line) < min_len or line in seen: continue
        seen.add(line)
        result.append(line)
    return result

def get_async_rag_data(query: str) -> str:
    cached = RAG_CACHE.get(query)
    if cached and time.time() - cached[0] < 1800: return cached[1]

    res, lock = {}, threading.Lock()

    def run_task(key: str, fn, *args):
        try:
            val = fn(*args)
            with lock: res[key] = val or ""
        except:
            pass

    tasks = [("wiki_ja", get_wikipedia, query), ("bing", fetch_bing_snippets, query + " 概要"), ("ddg", fetch_ddg_snippets, query), ("subcul", fetch_subculture, query)]
    threads = [threading.Thread(target=run_task, args=(k, fn, *a), daemon=True) for k, fn, *a in tasks]
    for t in threads: t.start()
    for t in threads: t.join(timeout=8)

    wiki_ja = res.get("wiki_ja", "").strip()
    web_hits = [res.get(k, "").strip() for k in ["bing", "ddg", "subcul"]]
    merged_web = "\n".join(deduplicate_lines("\n".join(web_hits).splitlines()))

    parts = []
    if wiki_ja: parts.append(f"[Wikipedia JA]\n{wiki_ja}")
    if merged_web: parts.append(f"[Web Search]\n{merged_web}")
    
    final = "\n\n".join(parts)
    RAG_CACHE[query] = (time.time(), final)
    return final