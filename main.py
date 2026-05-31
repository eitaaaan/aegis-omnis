#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# main.py — S-01 v128.1 Aegis Omnis — エントリポイント・COMMAND REGISTRY・run()
from __future__ import annotations
from s01_config import *
from s01_learning import *
from s01_persona import *
from s01_rag import *
from s01_lyrics import search_lyrics_absolute
from s01_midi import handle_midi, play_singularity
from s01_kb import handle_kb
from s01_spi import handle_spi
from s01_handlers import *
from s01_chess import handle_chess
from s01_shogi import handle_shogi
from s01_mahjong import handle_mahjong

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
            # ★ ペルソナが設定されている場合（デフォルト以外）は常にcomplexとして扱う
            # estimate_complexityは短い入力を「simple」と誤判定するため、
            # ペルソナ会話では入力長に関わらず常にfull品質で生成する
            _default_persona = get_persona(1)
            _is_persona_active = (p.get("name") != _default_persona.get("name"))
            complexity = "complex" if _is_persona_active else estimate_complexity(user_text)
            is_complex = complexity == "complex"
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
                            rag_snippet = f"\n\n【Web参照情報（参考程度に使え。ここにない事実を創作するな）】:\n{_rag[:500]}\n"
                    except Exception:
                        pass
                persona_style_block = p['style']
                _is_late_witt = p['name'] == "後期ウィトゲンシュタイン"
                if _is_late_witt:
                    sys_content = (
                        f"あなたは{p['name']}。一人称:{p.get('first_person','私')}。ユーザーは{USER_NAME}。\n"
                        f"【口調・スタイル（厳守）】{persona_style_block}\n"
                        f"【絶対禁止】番号付きリスト・箇条書きを使うな。\n"
                        f"【絶対禁止】比喩・例えは返答全体で1個のみ。2個目が出た時点で失格。\n"
                        f"【絶対禁止】複数の観点・側面・文脈を並列列挙するな。一つのことをじっと見つめよ。\n"
                        f"【必須】長々と語るな。3〜4段落、各段落3〜4文を目安に、静かに・深く語れ。\n"
                        f"【必須】最後の文を「。」で自然に結論づけて完結させること。"
                        + rag_snippet
                    )
                else:
                    sys_content = (
                        f"あなたは{p['name']}。一人称:{p.get('first_person','私')}。ユーザーは{USER_NAME}。\n"
                        f"【口調・スタイル（厳守）】{persona_style_block}\n"
                        f"【絶対禁止】番号付きリスト・箇条書きを使うな。\n"
                        f"【絶対禁止】比喩・例えを一度の返答で3つ以上連続して使うな。1〜2個を深く展開せよ。\n"
                        f"【絶対禁止】「まるで〜のようなものだ」という同一構文を連続3回以上使うな。"
                        f"比喩は使ってよいが、毎回異なる対象・角度で表現すること。\n"
                        f"【必須】深く・長く語ること。思考の展開、具体例、反論、歴史的文脈、個人的省察を織り交ぜよ。\n"
                        f"【必須】最後の文を「。」で自然に結論づけて完結させること。"
                        + rag_snippet
                    )
                d_tokens = -1
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
        for f in glob.glob("ytdl_y_*"): os.remove(f); removed += 1
        for f in glob.glob("tts_*.mp3"): os.remove(f); removed += 1
        for f in glob.glob("aegis_*.md"): os.remove(f); removed += 1
        for f in glob.glob("aegis_export_*.*"): os.remove(f); removed += 1
        for f in glob.glob("*.mid"): os.remove(f); removed += 1
        for f in glob.glob("*.wav"): os.remove(f); removed += 1
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
            rows.append(f"{C['y']}── /s 1〜{max(PERSONA_MAP)} 西洋哲学者一覧 ──{C['w']}")
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
            return f"{C['r']}ID: 1-{max(PERSONA_MAP)} (1=ソクラテス〜{max(PERSONA_MAP)}=ロールズ){C['w']}"
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
                complexity = estimate_complexity(raw)
                model_choice = select_model(raw)  # ★[修正/main-1] MODEL_NAME固定→select_model使用
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
            if POWER_MODE == "ultra":
                traceback.print_exc()

if __name__ == "__main__":
    run()




