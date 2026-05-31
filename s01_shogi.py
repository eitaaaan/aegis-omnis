#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# s01_shogi.py — 将棋エンジン・AI・GameCommentator・curses UI
from __future__ import annotations
import curses, random
from s01_config import C
from s01_rag import stream_response
from s01_persona import get_persona

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
                # ★ 追加哲学者
                "ベーコン","パスカル","ルソー","ヴォルテール","マキャベリ",
                "フロイト","ユング","フーコー","アレント","レヴィ＝ストロース",
                "デリダ","ロールズ",
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


