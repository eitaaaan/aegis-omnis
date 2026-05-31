#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# s01_chess.py — チェスエンジン・AI・curses UI
from __future__ import annotations
import curses, random
from s01_config import C

class ChessEngine:
    """本格的なチェスエンジン。完全な駒移動バリデーション・チェック/チェックメイト検出・特殊手対応。"""

    UNICODE_PIECES = {
        "wK": "♔", "wQ": "♕", "wR": "♖", "wB": "♗", "wN": "♘", "wP": "♙",
        "bK": "♚", "bQ": "♛", "bR": "♜", "bB": "♝", "bN": "♞", "bP": "♟",
    }
    ASCII_PIECES = {
        "wK": "K", "wQ": "Q", "wR": "R", "wB": "B", "wN": "N", "wP": "P",
        "bK": "k", "bQ": "q", "bR": "r", "bB": "b", "bN": "n", "bP": "p",
    }

    def __init__(self, use_unicode: bool = True):
        self.use_unicode = use_unicode
        self.reset()

    def reset(self):
        self.board: list[list[str | None]] = self._init_board()
        self.turn: str = "w"   # "w" or "b"
        self.castling_rights: dict = {"wK": True, "wQ": True, "bK": True, "bQ": True}
        self.en_passant: tuple | None = None   # (row, col) or None
        self.move_history: list[str] = []
        self.captured: dict = {"w": [], "b": []}
        self.halfmove_clock: int = 0
        self.fullmove: int = 1
        self.game_over: bool = False
        self.result: str = ""

    def _init_board(self) -> list[list]:
        b = [[None] * 8 for _ in range(8)]
        order = ["R", "N", "B", "Q", "K", "B", "N", "R"]
        for c, p in enumerate(order):
            b[0][c] = f"b{p}"
            b[7][c] = f"w{p}"
        for c in range(8):
            b[1][c] = "bP"
            b[6][c] = "wP"
        return b

    def piece_symbol(self, piece: str) -> str:
        if self.use_unicode:
            return self.UNICODE_PIECES.get(piece, "?")
        return self.ASCII_PIECES.get(piece, "?")

    def board_str(self, highlight: list[tuple] = None) -> str:
        highlight = highlight or []
        hl_set = set(highlight)
        lines = []
        sep_line = "  +" + "---+" * 8
        col_labels = "    a   b   c   d   e   f   g   h"
        lines.append(col_labels)
        lines.append(sep_line)
        for r in range(8):
            row_num = 8 - r
            cells = []
            for c in range(8):
                piece = self.board[r][c]
                sym = self.piece_symbol(piece) if piece else " "
                if (r, c) in hl_set:
                    cells.append(f"\033[43m {sym} \033[0m")
                elif (r + c) % 2 == 0:
                    cells.append(f"\033[47m {sym} \033[0m")
                else:
                    cells.append(f"\033[100m {sym} \033[0m")
            lines.append(f"{row_num} |{'|'.join(cells)}|")
            lines.append(sep_line)
        lines.append(col_labels)
        return "\n".join(lines)

    def parse_sq(self, s: str) -> tuple | None:
        s = s.strip().lower()
        if len(s) != 2: return None
        c = ord(s[0]) - ord('a')
        r = 8 - int(s[1])
        if not (0 <= r <= 7 and 0 <= c <= 7): return None
        return (r, c)

    def sq_name(self, r: int, c: int) -> str:
        return chr(ord('a') + c) + str(8 - r)

    def _enemy(self, color: str) -> str:
        return "b" if color == "w" else "w"

    def _piece_color(self, piece: str | None) -> str | None:
        return piece[0] if piece else None

    def _piece_type(self, piece: str | None) -> str | None:
        return piece[1] if piece else None

    def _on_board(self, r: int, c: int) -> bool:
        return 0 <= r <= 7 and 0 <= c <= 7

    def pseudo_legal_moves(self, r: int, c: int) -> list[tuple]:
        piece = self.board[r][c]
        if not piece: return []
        color = piece[0]
        ptype = piece[1]
        moves = []

        if ptype == "P":
            moves = self._pawn_moves(r, c, color)
        elif ptype == "N":
            moves = self._knight_moves(r, c, color)
        elif ptype == "B":
            moves = self._sliding_moves(r, c, color, [(1,1),(1,-1),(-1,1),(-1,-1)])
        elif ptype == "R":
            moves = self._sliding_moves(r, c, color, [(1,0),(-1,0),(0,1),(0,-1)])
        elif ptype == "Q":
            moves = self._sliding_moves(r, c, color, [(1,1),(1,-1),(-1,1),(-1,-1),(1,0),(-1,0),(0,1),(0,-1)])
        elif ptype == "K":
            moves = self._king_moves(r, c, color)
        return moves

    def _pawn_moves(self, r: int, c: int, color: str) -> list[tuple]:
        moves = []
        d = -1 if color == "w" else 1
        start_row = 6 if color == "w" else 1
        # 前進
        nr = r + d
        if self._on_board(nr, c) and not self.board[nr][c]:
            moves.append((nr, c))
            # 初期2マス
            if r == start_row and not self.board[r + 2*d][c]:
                moves.append((r + 2*d, c))
        # 斜め攻撃
        for dc in (-1, 1):
            nc = c + dc
            if self._on_board(nr, nc):
                target = self.board[nr][nc]
                if target and target[0] != color:
                    moves.append((nr, nc))
                # アンパッサン
                if self.en_passant == (nr, nc):
                    moves.append((nr, nc))
        return moves

    def _knight_moves(self, r: int, c: int, color: str) -> list[tuple]:
        moves = []
        for dr, dc in [(-2,-1),(-2,1),(-1,-2),(-1,2),(1,-2),(1,2),(2,-1),(2,1)]:
            nr, nc = r+dr, c+dc
            if self._on_board(nr, nc):
                t = self.board[nr][nc]
                if not t or t[0] != color:
                    moves.append((nr, nc))
        return moves

    def _sliding_moves(self, r: int, c: int, color: str, dirs: list) -> list[tuple]:
        moves = []
        for dr, dc in dirs:
            nr, nc = r+dr, c+dc
            while self._on_board(nr, nc):
                t = self.board[nr][nc]
                if t:
                    if t[0] != color: moves.append((nr, nc))
                    break
                moves.append((nr, nc))
                nr += dr; nc += dc
        return moves

    def _king_moves(self, r: int, c: int, color: str) -> list[tuple]:
        moves = []
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0: continue
                nr, nc = r+dr, c+dc
                if self._on_board(nr, nc):
                    t = self.board[nr][nc]
                    if not t or t[0] != color:
                        moves.append((nr, nc))
        # キャスリング
        back_rank = 7 if color == "w" else 0
        if r == back_rank and c == 4:
            # キングサイド
            if self.castling_rights[f"{color}K"]:
                if (not self.board[back_rank][5] and not self.board[back_rank][6]
                        and self.board[back_rank][7] == f"{color}R"):
                    if not self._sq_attacked(back_rank, 4, self._enemy(color)) \
                            and not self._sq_attacked(back_rank, 5, self._enemy(color)) \
                            and not self._sq_attacked(back_rank, 6, self._enemy(color)):
                        moves.append((back_rank, 6))
            # クイーンサイド
            if self.castling_rights[f"{color}Q"]:
                if (not self.board[back_rank][3] and not self.board[back_rank][2]
                        and not self.board[back_rank][1]
                        and self.board[back_rank][0] == f"{color}R"):
                    if not self._sq_attacked(back_rank, 4, self._enemy(color)) \
                            and not self._sq_attacked(back_rank, 3, self._enemy(color)) \
                            and not self._sq_attacked(back_rank, 2, self._enemy(color)):
                        moves.append((back_rank, 2))
        return moves

    def _sq_attacked(self, r: int, c: int, by_color: str) -> bool:
        """by_color の駒が (r,c) を攻撃しているか"""
        enemy = by_color
        # ポーン攻撃
        pd = 1 if enemy == "w" else -1
        for dc in (-1, 1):
            nr, nc = r+pd, c+dc
            if self._on_board(nr, nc) and self.board[nr][nc] == f"{enemy}P":
                return True
        # ナイト
        for dr, dc in [(-2,-1),(-2,1),(-1,-2),(-1,2),(1,-2),(1,2),(2,-1),(2,1)]:
            nr, nc = r+dr, c+dc
            if self._on_board(nr, nc) and self.board[nr][nc] == f"{enemy}N":
                return True
        # 直線・斜め
        for dr, dc in [(1,0),(-1,0),(0,1),(0,-1)]:
            nr, nc = r+dr, c+dc
            while self._on_board(nr, nc):
                t = self.board[nr][nc]
                if t:
                    if t[0] == enemy and t[1] in ("R", "Q"): return True
                    break
                nr += dr; nc += dc
        for dr, dc in [(1,1),(1,-1),(-1,1),(-1,-1)]:
            nr, nc = r+dr, c+dc
            while self._on_board(nr, nc):
                t = self.board[nr][nc]
                if t:
                    if t[0] == enemy and t[1] in ("B", "Q"): return True
                    break
                nr += dr; nc += dc
        # キング
        for dr in (-1,0,1):
            for dc in (-1,0,1):
                if dr == 0 and dc == 0: continue
                nr, nc = r+dr, c+dc
                if self._on_board(nr, nc) and self.board[nr][nc] == f"{enemy}K":
                    return True
        return False

    def _find_king(self, color: str) -> tuple | None:
        for r in range(8):
            for c in range(8):
                if self.board[r][c] == f"{color}K":
                    return (r, c)
        return None

    def in_check(self, color: str) -> bool:
        kpos = self._find_king(color)
        if kpos is None: return False
        return self._sq_attacked(kpos[0], kpos[1], self._enemy(color))

    def _apply_move_temp(self, r: int, c: int, tr: int, tc: int) -> dict:
        """合法性チェックなしで仮に駒を動かし、undo用のsavedを返す (AI探索用)。"""
        piece = self.board[r][c]
        target = self.board[tr][tc]
        saved = {
            "from": (r, c, piece),
            "to": (tr, tc, target),
            "en_passant": self.en_passant,
            "castling_rights": dict(self.castling_rights),
            "halfmove_clock": self.halfmove_clock,
        }

        # アンパッサン捕獲
        ep_capture = None
        if piece and piece[1] == "P" and self.en_passant == (tr, tc):
            ep_r = tr + (1 if piece[0] == "w" else -1)
            ep_capture = (ep_r, tc, self.board[ep_r][tc])
            self.board[ep_r][tc] = None
        saved["ep_capture"] = ep_capture

        # キャスリング時ルーク移動
        rook_move = None
        if piece and piece[1] == "K" and abs(tc - c) == 2:
            back_rank = r
            if tc == 6:
                rook_move = (back_rank, 7, back_rank, 5, self.board[back_rank][7])
                self.board[back_rank][5] = self.board[back_rank][7]
                self.board[back_rank][7] = None
            elif tc == 2:
                rook_move = (back_rank, 0, back_rank, 3, self.board[back_rank][0])
                self.board[back_rank][3] = self.board[back_rank][0]
                self.board[back_rank][0] = None
        saved["rook_move"] = rook_move

        self.board[r][c] = None
        self.board[tr][tc] = piece

        # プロモーション (常にクイーンに昇格)
        if piece and piece[1] == "P" and (tr == 0 or tr == 7):
            self.board[tr][tc] = f"{piece[0]}Q"

        # アンパッサン更新
        self.en_passant = None
        if piece and piece[1] == "P" and abs(tr - r) == 2:
            self.en_passant = ((r + tr) // 2, c)

        # キャスリング権更新
        if piece and piece[1] == "K":
            color = piece[0]
            self.castling_rights[f"{color}K"] = False
            self.castling_rights[f"{color}Q"] = False
        if piece and piece[1] == "R":
            color = piece[0]
            back_rank = 7 if color == "w" else 0
            if r == back_rank and c == 7: self.castling_rights[f"{color}K"] = False
            if r == back_rank and c == 0: self.castling_rights[f"{color}Q"] = False

        return saved

    def legal_moves(self, color: str) -> list[tuple]:
        """(from_r, from_c, to_r, to_c) の合法手リスト"""
        result = []
        for r in range(8):
            for c in range(8):
                piece = self.board[r][c]
                if not piece or piece[0] != color: continue
                for tr, tc in self.pseudo_legal_moves(r, c):
                    saved = self._apply_move_temp(r, c, tr, tc)
                    if not self.in_check(color):
                        result.append((r, c, tr, tc))
                    self._undo_move_temp(saved)
        return result

    def _apply_move_temp(self, r, c, tr, tc):
        """一時的に手を適用し、巻き戻し用データを返す"""
        piece = self.board[r][c]
        target = self.board[tr][tc]
        saved = {
            "from": (r, c, piece),
            "to": (tr, tc, target),
            "en_passant": self.en_passant,
            "castling_rights": dict(self.castling_rights),
            "ep_capture": None,
        }
        self.board[r][c] = None
        self.board[tr][tc] = piece

        # アンパッサン
        if piece[1] == "P" and self.en_passant == (tr, tc):
            ep_r = tr + (1 if piece[0] == "w" else -1)
            saved["ep_capture"] = (ep_r, tc, self.board[ep_r][tc])
            self.board[ep_r][tc] = None

        # キャスリング時のルーク移動
        if piece[1] == "K" and abs(tc - c) == 2:
            back_rank = r
            if tc == 6:  # キングサイド
                saved["rook_move"] = (back_rank, 7, back_rank, 5, self.board[back_rank][7])
                self.board[back_rank][5] = self.board[back_rank][7]
                self.board[back_rank][7] = None
            elif tc == 2:  # クイーンサイド
                saved["rook_move"] = (back_rank, 0, back_rank, 3, self.board[back_rank][0])
                self.board[back_rank][3] = self.board[back_rank][0]
                self.board[back_rank][0] = None

        self.en_passant = None
        return saved

    def _undo_move_temp(self, saved):
        r, c, piece = saved["from"]
        tr, tc, target = saved["to"]
        self.board[r][c] = piece
        self.board[tr][tc] = target
        self.en_passant = saved["en_passant"]
        self.castling_rights = saved["castling_rights"]
        if saved.get("ep_capture"):
            er, ec, ep = saved["ep_capture"]
            self.board[er][ec] = ep
        if saved.get("rook_move"):
            rr, rc, nrr, nrc, rp = saved["rook_move"]
            self.board[rr][rc] = rp
            self.board[nrr][nrc] = None

    def move_sq(self, r: int, c: int, tr: int, tc: int, promotion: str = "Q") -> tuple[bool, str]:
        """駒を移動する。成功時 (True, 棋譜表記)、失敗時 (False, エラー文字列)"""
        piece = self.board[r][c]
        if not piece:
            return False, "その位置に駒がありません"
        if piece[0] != self.turn:
            return False, f"{'白' if self.turn=='w' else '黒'}の手番です"
        legal = self.legal_moves(self.turn)
        if (r, c, tr, tc) not in legal:
            return False, "その手は合法ではありません"

        target = self.board[tr][tc]
        notation = self._build_notation(r, c, tr, tc, piece, target, promotion)

        # アンパッサン
        ep_capture_pos = None
        if piece[1] == "P" and self.en_passant == (tr, tc):
            ep_r = tr + (1 if piece[0] == "w" else -1)
            ep_capture_pos = (ep_r, tc)
            cap = self.board[ep_r][tc]
            if cap: self.captured[self.turn].append(cap)
            self.board[ep_r][tc] = None

        if target:
            self.captured[self.turn].append(target)

        self.board[r][c] = None
        self.board[tr][tc] = piece

        # キャスリング
        if piece[1] == "K":
            color = piece[0]
            back_rank = 7 if color == "w" else 0
            if tc == 6 and c == 4:
                self.board[back_rank][5] = self.board[back_rank][7]
                self.board[back_rank][7] = None
            elif tc == 2 and c == 4:
                self.board[back_rank][3] = self.board[back_rank][0]
                self.board[back_rank][0] = None
            self.castling_rights[f"{color}K"] = False
            self.castling_rights[f"{color}Q"] = False

        # ルーク移動 → キャスリング権失効
        if piece[1] == "R":
            color = piece[0]
            back_rank = 7 if color == "w" else 0
            if r == back_rank and c == 7: self.castling_rights[f"{color}K"] = False
            if r == back_rank and c == 0: self.castling_rights[f"{color}Q"] = False

        # アンパッサン設定
        self.en_passant = None
        if piece[1] == "P" and abs(tr - r) == 2:
            self.en_passant = ((r + tr) // 2, c)

        # プロモーション
        if piece[1] == "P" and (tr == 0 or tr == 7):
            self.board[tr][tc] = f"{piece[0]}{promotion}"
            notation += f"={promotion}"

        # チェック確認
        enemy = self._enemy(self.turn)
        check = self.in_check(enemy)
        self.turn = enemy
        if check:
            legal_next = self.legal_moves(self.turn)
            if not legal_next:
                notation += "#"
                self.game_over = True
                winner = "白" if self.turn == "b" else "黒"
                self.result = f"チェックメイト！{winner}の勝利"
            else:
                notation += "+"
        else:
            legal_next = self.legal_moves(self.turn)
            if not legal_next:
                notation += " (ステールメイト)"
                self.game_over = True
                self.result = "ステールメイト（引き分け）"

        self.move_history.append(notation)
        if self.turn == "w": self.fullmove += 1
        return True, notation

    def _build_notation(self, r, c, tr, tc, piece, target, promotion) -> str:
        ptype = piece[1]
        dest = self.sq_name(tr, tc)
        if ptype == "K" and abs(tc - c) == 2:
            return "O-O" if tc == 6 else "O-O-O"
        cap = "x" if target or (ptype == "P" and self.en_passant == (tr, tc)) else ""
        if ptype == "P":
            if cap:
                return f"{chr(ord('a')+c)}{cap}{dest}"
            return dest
        return f"{ptype}{cap}{dest}"

    def legal_targets(self, r: int, c: int) -> list[tuple]:
        """(r,c) の駒が動ける合法手の移動先リスト"""
        all_legal = self.legal_moves(self.turn)
        return [(tr, tc) for (fr, fc, tr, tc) in all_legal if fr == r and fc == c]

    def status_str(self) -> str:
        turn_str = "白(White)" if self.turn == "w" else "黒(Black)"
        check_str = " 【チェック！】" if self.in_check(self.turn) else ""
        cap_w = " ".join(self.piece_symbol(p) for p in self.captured["w"]) or "なし"
        cap_b = " ".join(self.piece_symbol(p) for p in self.captured["b"]) or "なし"
        move_count = (self.fullmove - 1) * 2 + (0 if self.turn == "w" else 1)
        hist = "  ".join(self.move_history[-6:]) if self.move_history else "なし"
        lines = [
            f"手番: {turn_str}{check_str}   ({move_count}手目)",
            f"白が取った駒: {cap_b}   黒が取った駒: {cap_w}",
            f"直近の手: {hist}",
        ]
        return "\n".join(lines)



# ===== チェス AI エンジン =====

class ChessAI:
    """
    チェスAI。4段階の難易度に対応。
      easy      : ランダム手
      middle    : depth=1 minimax + 基本評価
      hard      : depth=3 minimax + alpha-beta + 評価関数
      very_hard : depth=4 minimax + alpha-beta + 評価関数 + ランダム揺らぎなし
    """

    # 駒の基本価値
    PIECE_VALUE = {"P": 100, "N": 320, "B": 330, "R": 500, "Q": 900, "K": 20000}

    # 駒ごとのポジションボーナス (白視点, 行0=黒側, 行7=白側)
    _PST = {
        "P": [
            [ 0,  0,  0,  0,  0,  0,  0,  0],
            [50, 50, 50, 50, 50, 50, 50, 50],
            [10, 10, 20, 30, 30, 20, 10, 10],
            [ 5,  5, 10, 25, 25, 10,  5,  5],
            [ 0,  0,  0, 20, 20,  0,  0,  0],
            [ 5, -5,-10,  0,  0,-10, -5,  5],
            [ 5, 10, 10,-20,-20, 10, 10,  5],
            [ 0,  0,  0,  0,  0,  0,  0,  0],
        ],
        "N": [
            [-50,-40,-30,-30,-30,-30,-40,-50],
            [-40,-20,  0,  0,  0,  0,-20,-40],
            [-30,  0, 10, 15, 15, 10,  0,-30],
            [-30,  5, 15, 20, 20, 15,  5,-30],
            [-30,  0, 15, 20, 20, 15,  0,-30],
            [-30,  5, 10, 15, 15, 10,  5,-30],
            [-40,-20,  0,  5,  5,  0,-20,-40],
            [-50,-40,-30,-30,-30,-30,-40,-50],
        ],
        "B": [
            [-20,-10,-10,-10,-10,-10,-10,-20],
            [-10,  0,  0,  0,  0,  0,  0,-10],
            [-10,  0,  5, 10, 10,  5,  0,-10],
            [-10,  5,  5, 10, 10,  5,  5,-10],
            [-10,  0, 10, 10, 10, 10,  0,-10],
            [-10, 10, 10, 10, 10, 10, 10,-10],
            [-10,  5,  0,  0,  0,  0,  5,-10],
            [-20,-10,-10,-10,-10,-10,-10,-20],
        ],
        "R": [
            [ 0,  0,  0,  0,  0,  0,  0,  0],
            [ 5, 10, 10, 10, 10, 10, 10,  5],
            [-5,  0,  0,  0,  0,  0,  0, -5],
            [-5,  0,  0,  0,  0,  0,  0, -5],
            [-5,  0,  0,  0,  0,  0,  0, -5],
            [-5,  0,  0,  0,  0,  0,  0, -5],
            [-5,  0,  0,  0,  0,  0,  0, -5],
            [ 0,  0,  0,  5,  5,  0,  0,  0],
        ],
        "Q": [
            [-20,-10,-10, -5, -5,-10,-10,-20],
            [-10,  0,  0,  0,  0,  0,  0,-10],
            [-10,  0,  5,  5,  5,  5,  0,-10],
            [ -5,  0,  5,  5,  5,  5,  0, -5],
            [  0,  0,  5,  5,  5,  5,  0, -5],
            [-10,  5,  5,  5,  5,  5,  0,-10],
            [-10,  0,  5,  0,  0,  0,  0,-10],
            [-20,-10,-10, -5, -5,-10,-10,-20],
        ],
        "K": [
            [-30,-40,-40,-50,-50,-40,-40,-30],
            [-30,-40,-40,-50,-50,-40,-40,-30],
            [-30,-40,-40,-50,-50,-40,-40,-30],
            [-30,-40,-40,-50,-50,-40,-40,-30],
            [-20,-30,-30,-40,-40,-30,-30,-20],
            [-10,-20,-20,-20,-20,-20,-20,-10],
            [ 20, 20,  0,  0,  0,  0, 20, 20],
            [ 20, 30, 10,  0,  0, 10, 30, 20],
        ],
    }

    DIFFICULTY_SETTINGS = {
        "easy":      {"depth": 0, "random_rate": 1.0},   # 完全ランダム
        "middle":    {"depth": 1, "random_rate": 0.2},   # depth1 + 20%ランダム
        "hard":      {"depth": 3, "random_rate": 0.0},   # depth3 alpha-beta
        "very_hard": {"depth": 4, "random_rate": 0.0},   # depth4 alpha-beta
    }

    def __init__(self, difficulty: str = "middle", color: str = "b"):
        self.difficulty = difficulty
        self.color = color  # AIが担当する色 ("w" or "b")
        s = self.DIFFICULTY_SETTINGS.get(difficulty, self.DIFFICULTY_SETTINGS["middle"])
        self.depth = s["depth"]
        self.random_rate = s["random_rate"]

    def _pst_score(self, piece: str, r: int, c: int) -> int:
        """駒のポジションスコア (白視点)"""
        color, ptype = piece[0], piece[1]
        table = self._PST.get(ptype)
        if table is None:
            return 0
        if color == "w":
            return table[r][c]
        else:
            return table[7 - r][c]

    def evaluate(self, g: "ChessEngine") -> int:
        """盤面評価 (正=白有利, 負=黒有利)"""
        score = 0
        for r in range(8):
            for c in range(8):
                piece = g.board[r][c]
                if not piece:
                    continue
                color, ptype = piece[0], piece[1]
                val = self.PIECE_VALUE.get(ptype, 0) + self._pst_score(piece, r, c)
                score += val if color == "w" else -val
        return score

    def _all_legal_moves(self, g: "ChessEngine", color: str) -> list[tuple]:
        return g.legal_moves(color)

    def _minimax(self, g: "ChessEngine", depth: int, alpha: int, beta: int, maximizing: bool) -> int:
        if depth == 0 or g.game_over:
            return self.evaluate(g)

        color = "w" if maximizing else "b"
        moves = self._all_legal_moves(g, color)
        if not moves:
            return self.evaluate(g)

        if maximizing:
            best = -10**9
            for fr, fc, tr, tc in moves:
                saved = g._apply_move_temp(fr, fc, tr, tc)
                prev_turn = g.turn
                g.turn = "b"
                val = self._minimax(g, depth - 1, alpha, beta, False)
                g.turn = prev_turn
                g._undo_move_temp(saved)
                best = max(best, val)
                alpha = max(alpha, val)
                if beta <= alpha:
                    break
            return best
        else:
            best = 10**9
            for fr, fc, tr, tc in moves:
                saved = g._apply_move_temp(fr, fc, tr, tc)
                prev_turn = g.turn
                g.turn = "w"
                val = self._minimax(g, depth - 1, alpha, beta, True)
                g.turn = prev_turn
                g._undo_move_temp(saved)
                best = min(best, val)
                beta = min(beta, val)
                if beta <= alpha:
                    break
            return best

    def choose_move(self, g: "ChessEngine") -> tuple | None:
        """AIが次の手を選んで (fr, fc, tr, tc) を返す。手がなければ None。"""
        moves = self._all_legal_moves(g, self.color)
        if not moves:
            return None

        # easy: 完全ランダム
        if self.difficulty == "easy":
            return random.choice(moves)

        # middle/hard/very_hard: random_rate の確率でランダム手
        if self.random_rate > 0 and random.random() < self.random_rate:
            return random.choice(moves)

        # minimax で最善手を探す
        maximizing = (self.color == "w")
        best_val = -10**9 if maximizing else 10**9
        best_moves = []

        for fr, fc, tr, tc in moves:
            saved = g._apply_move_temp(fr, fc, tr, tc)
            prev_turn = g.turn
            g.turn = "b" if self.color == "w" else "w"
            val = self._minimax(g, self.depth - 1, -10**9, 10**9, not maximizing)
            g.turn = prev_turn
            g._undo_move_temp(saved)

            if maximizing:
                if val > best_val:
                    best_val = val
                    best_moves = [(fr, fc, tr, tc)]
                elif val == best_val:
                    best_moves.append((fr, fc, tr, tc))
            else:
                if val < best_val:
                    best_val = val
                    best_moves = [(fr, fc, tr, tc)]
                elif val == best_val:
                    best_moves.append((fr, fc, tr, tc))

        return random.choice(best_moves) if best_moves else random.choice(moves)


# ===== チェス curses マウス UI =====

# ── レイアウト定数 ──────────────────────────────────────────
_CW   = 5   # マス幅 (chars)  ← Unicode駒の表示幅を考慮
_CH   = 3   # マス高 (lines)
_BX   = 4   # 盤面左端 (col offset) ← 行番号 "8 " 分
_BY   = 2   # 盤面上端 (row offset) ← タイトル分
_INFO_X = _BX + _CW * 8 + 2   # 右パネル開始列

# ── カラーペア ID ────────────────────────────────────────────
_CP_LIGHT       = 1   # 白マス
_CP_DARK        = 2   # 黒マス
_CP_SELECTED    = 3   # 選択中マス
_CP_LEGAL       = 4   # 合法手マス
_CP_LAST_MOVE   = 5   # 直前の移動元/先
_CP_CHECK       = 6   # チェック中のキング
_CP_TITLE       = 7   # タイトルバー
_CP_PANEL       = 8   # 右パネル
_CP_BTN         = 9   # ボタン通常
_CP_BTN_HL      = 10  # ボタンハイライト
_CP_STATUS_OK   = 11  # ステータス (通常)
_CP_STATUS_WARN = 12  # ステータス (警告)
_CP_PROMO       = 13  # プロモーションポップ
_CP_COMMENT     = 14  # ペルソナテロップ

def _init_colors():
    curses.start_color()
    curses.use_default_colors()
    # light squares: dark text on cream
    curses.init_pair(_CP_LIGHT,       curses.COLOR_BLACK,   curses.COLOR_WHITE)
    # dark squares: white text on dark green
    curses.init_pair(_CP_DARK,        curses.COLOR_WHITE,   curses.COLOR_GREEN)
    # selected: black on yellow
    curses.init_pair(_CP_SELECTED,    curses.COLOR_BLACK,   curses.COLOR_YELLOW)
    # legal move dot: black on cyan
    curses.init_pair(_CP_LEGAL,       curses.COLOR_BLACK,   curses.COLOR_CYAN)
    # last move: black on blue
    curses.init_pair(_CP_LAST_MOVE,   curses.COLOR_WHITE,   curses.COLOR_BLUE)
    # check: white on red
    curses.init_pair(_CP_CHECK,       curses.COLOR_WHITE,   curses.COLOR_RED)
    # title bar: black on white
    curses.init_pair(_CP_TITLE,       curses.COLOR_BLACK,   curses.COLOR_WHITE)
    # right panel: white on black (default)
    curses.init_pair(_CP_PANEL,       curses.COLOR_WHITE,   -1)
    # button
    curses.init_pair(_CP_BTN,         curses.COLOR_BLACK,   curses.COLOR_WHITE)
    curses.init_pair(_CP_BTN_HL,      curses.COLOR_WHITE,   curses.COLOR_MAGENTA)
    # status bar
    curses.init_pair(_CP_STATUS_OK,   curses.COLOR_BLACK,   curses.COLOR_CYAN)
    curses.init_pair(_CP_STATUS_WARN, curses.COLOR_WHITE,   curses.COLOR_RED)
    # promotion popup
    curses.init_pair(_CP_PROMO,       curses.COLOR_BLACK,   curses.COLOR_YELLOW)
    curses.init_pair(_CP_COMMENT,     curses.COLOR_BLACK,   curses.COLOR_MAGENTA)  # テロップ


def _chess_curses_main(stdscr, g: "ChessEngine", ai: "ChessAI | None" = None,
                       commentator: "GameCommentator | None" = None):
    """curses ループ本体。マウスクリックでチェスを操作する。"""
    _init_colors()
    curses.curs_set(0)
    curses.mousemask(curses.ALL_MOUSE_EVENTS | curses.REPORT_MOUSE_POSITION)
    curses.mouseinterval(0)
    stdscr.keypad(True)
    stdscr.timeout(80)   # ms – リフレッシュ間隔

    selected: tuple | None = None       # 選択中マス (r, c)
    legal_tgts: list[tuple] = []        # 現選択駒の合法手
    last_move: list[tuple] = []         # 直前の移動元/先

    # AI難易度ラベル
    _diff_labels = {"easy": "Easy", "middle": "Middle", "hard": "Hard", "very_hard": "Very Hard"}
    if ai:
        ai_label = _diff_labels.get(ai.difficulty, ai.difficulty)
        status_msg = f"♟ AI対戦モード [{ai_label}] — 白(あなた)から開始。駒をクリック！"
    else:
        status_msg = "♟ クリックして駒を選択してください"
    status_warn = False
    undo_stack: list[dict] = []
    promo_pending: tuple | None = None  # (fr, fc, tr, tc) プロモーション待ち

    # ── ボタン定義 [(ラベル, action_key), ...] ─────────────────
    BUTTONS = [
        ("  New  ", "new"),
        ("  Undo ", "undo"),
        ("  Quit ", "quit"),
    ]

    def _snapshot():
        return {
            "board": [row[:] for row in g.board],
            "turn": g.turn,
            "castling_rights": dict(g.castling_rights),
            "en_passant": g.en_passant,
            "move_history": g.move_history[:],
            "captured": {"w": g.captured["w"][:], "b": g.captured["b"][:]},
            "fullmove": g.fullmove,
            "game_over": g.game_over,
            "result": g.result,
        }

    def _restore(snap):
        g.board            = snap["board"]
        g.turn             = snap["turn"]
        g.castling_rights  = snap["castling_rights"]
        g.en_passant       = snap["en_passant"]
        g.move_history     = snap["move_history"]
        g.captured         = snap["captured"]
        g.fullmove         = snap["fullmove"]
        g.game_over        = snap["game_over"]
        g.result           = snap["result"]

    def _sq_to_screen(r, c):
        """ボードマス (r, c) → curses 左上 (y, x)"""
        return (_BY + r * _CH, _BX + c * _CW)

    def _screen_to_sq(my, mx):
        """curses 座標 → ボードマス (r, c) or None"""
        r = (my - _BY) // _CH
        c = (mx - _BX) // _CW
        if 0 <= r <= 7 and 0 <= c <= 7:
            ry = my - (_BY + r * _CH)
            rx = mx - (_BX + c * _CW)
            if 0 <= ry < _CH and 0 <= rx < _CW:
                return (r, c)
        return None

    def _draw_cell(r, c, piece, color_pair, center_mark=""):
        """1マスを描画 (_CH lines × _CW cols)"""
        sy, sx = _sq_to_screen(r, c)
        sym = g.piece_symbol(piece) if piece else " "
        # 上段・下段: 空白
        try:
            stdscr.addstr(sy,       sx, " " * _CW, curses.color_pair(color_pair))
            stdscr.addstr(sy + 2,   sx, " " * _CW, curses.color_pair(color_pair))
            # 中段: 駒シンボル
            mid = center_mark if (not piece and center_mark) else sym
            line = f"  {mid}  " if len(mid) == 1 else f" {mid}  "
            line = line[:_CW]
            stdscr.addstr(sy + 1, sx, line, curses.color_pair(color_pair) | curses.A_BOLD)
        except curses.error:
            pass

    def _draw_board():
        king_pos = g._find_king(g.turn)
        in_chk   = g.in_check(g.turn)

        for r in range(8):
            for c in range(8):
                piece = g.board[r][c]
                base_light = (r + c) % 2 == 0

                if selected and (r, c) == selected:
                    cp = _CP_SELECTED
                elif (r, c) in legal_tgts:
                    cp = _CP_LEGAL
                elif (r, c) in last_move:
                    cp = _CP_LAST_MOVE
                elif in_chk and king_pos and (r, c) == king_pos:
                    cp = _CP_CHECK
                else:
                    cp = _CP_LIGHT if base_light else _CP_DARK

                mark = "·" if (r, c) in legal_tgts and not piece else ""
                _draw_cell(r, c, piece, cp, center_mark=mark)

        # 行ラベル (8〜1)
        for r in range(8):
            sy, _ = _sq_to_screen(r, 0)
            try:
                stdscr.addstr(sy + 1, _BX - 2, str(8 - r),
                              curses.color_pair(_CP_PANEL) | curses.A_BOLD)
            except curses.error:
                pass

        # 列ラベル (a〜h)
        col_y = _BY + 8 * _CH
        for c in range(8):
            _, sx = _sq_to_screen(0, c)
            try:
                stdscr.addstr(col_y, sx + 2, chr(ord('a') + c),
                              curses.color_pair(_CP_PANEL) | curses.A_BOLD)
            except curses.error:
                pass

    def _draw_title():
        turn_str = "♔ 白 (White)" if g.turn == "w" else "♚ 黒 (Black)"
        chk_str  = "  ⚠ チェック！" if g.in_check(g.turn) else ""
        move_n   = (g.fullmove - 1) * 2 + (0 if g.turn == "w" else 1)
        _diff_labels = {"easy": "Easy", "middle": "Middle", "hard": "Hard", "very_hard": "Very Hard"}
        ai_str = f"  [AI:{_diff_labels.get(ai.difficulty,'')}]" if ai else ""
        title = f"  ♟ チェス{ai_str}  {turn_str}{chk_str}   {move_n}手目  "
        try:
            stdscr.addstr(0, 0, title.ljust(80), curses.color_pair(_CP_TITLE) | curses.A_BOLD)
        except curses.error:
            pass

    def _draw_panel():
        """右パネル: 取得駒 / 手の記録 / ボタン"""
        px = _INFO_X
        h, w = stdscr.getmaxyx()

        # 取得駒
        cap_b_sym = " ".join(g.piece_symbol(p) for p in g.captured["w"][-8:]) or "なし"
        cap_w_sym = " ".join(g.piece_symbol(p) for p in g.captured["b"][-8:]) or "なし"
        try:
            stdscr.addstr(_BY,     px, "取:白→ " + cap_b_sym, curses.color_pair(_CP_PANEL))
            stdscr.addstr(_BY + 1, px, "取:黒→ " + cap_w_sym, curses.color_pair(_CP_PANEL))
        except curses.error:
            pass

        # 棋譜
        hist_y = _BY + 3
        try:
            stdscr.addstr(hist_y - 1, px, "── 棋譜 ──────────",
                          curses.color_pair(_CP_PANEL) | curses.A_DIM)
        except curses.error:
            pass
        hist = g.move_history
        panel_h = max(4, h - hist_y - 6)
        start_i = max(0, len(hist) - panel_h * 2)
        line_i  = 0
        for i in range(start_i, len(hist), 2):
            w_m = hist[i] if i < len(hist) else ""
            b_m = hist[i + 1] if i + 1 < len(hist) else ""
            num = i // 2 + 1
            line = f"{num:2d}. {w_m:<8s} {b_m}"
            try:
                stdscr.addstr(hist_y + line_i, px, line[:28], curses.color_pair(_CP_PANEL))
            except curses.error:
                pass
            line_i += 1
            if line_i >= panel_h:
                break

        # ボタン
        btn_y = h - 4
        btn_x = px
        _draw_buttons(btn_y, btn_x)

    def _draw_buttons(by, bx):
        for i, (label, _) in enumerate(BUTTONS):
            try:
                stdscr.addstr(by, bx + i * 10, label,
                              curses.color_pair(_CP_BTN) | curses.A_BOLD)
            except curses.error:
                pass

    def _btn_at(my, mx):
        """クリック座標がボタンに当たっていれば action_key を返す"""
        h, _ = stdscr.getmaxyx()
        by = h - 4
        bx = _INFO_X
        for i, (label, action) in enumerate(BUTTONS):
            lx = bx + i * 10
            if my == by and lx <= mx < lx + len(label):
                return action
        return None

    def _draw_status(msg, warn=False):
        h, w_max = stdscr.getmaxyx()
        cp = _CP_STATUS_WARN if warn else _CP_STATUS_OK
        line = f"  {msg}  "
        try:
            stdscr.addstr(h - 2, 0, line.ljust(w_max - 1), curses.color_pair(cp))
        except curses.error:
            pass

    def _draw_promotion_popup(color: str):
        """プロモーション選択ポップアップを描画し、クリック位置を返す"""
        pieces = [f"{color}Q", f"{color}R", f"{color}B", f"{color}N"]
        labels = ["クイーン", "ルーク", "ビショップ", "ナイト"]
        h, w_max = stdscr.getmaxyx()
        pw, ph = 52, 7
        py = h // 2 - ph // 2
        px_ = w_max // 2 - pw // 2

        cp = curses.color_pair(_CP_PROMO) | curses.A_BOLD
        try:
            stdscr.addstr(py,     px_, "╔" + "═"*(pw-2) + "╗", cp)
            stdscr.addstr(py + 1, px_, "║" + "  プロモーション駒を選んでクリック  ".center(pw-2) + "║", cp)
            stdscr.addstr(py + 2, px_, "║" + " " * (pw-2) + "║", cp)
            for i, (p, lbl) in enumerate(zip(pieces, labels)):
                sym = g.piece_symbol(p)
                cell = f" {sym} {lbl} "
                bx_ = px_ + 1 + i * 12
                stdscr.addstr(py + 3, bx_, cell.ljust(11), cp)
            stdscr.addstr(py + 4, px_, "║" + " " * (pw-2) + "║", cp)
            stdscr.addstr(py + 5, px_, "║" + "   (クリック or Q/R/B/N キー)   ".center(pw-2) + "║", cp)
            stdscr.addstr(py + 6, px_, "╚" + "═"*(pw-2) + "╝", cp)
        except curses.error:
            pass
        stdscr.refresh()

        # promo ボタン領域を返す: [(piece, y, x_start, x_end), ...]
        zones = []
        for i, p in enumerate(pieces):
            bx_ = px_ + 1 + i * 12
            zones.append((p[1], py + 3, bx_, bx_ + 11))
        return zones

    def _do_move(fr, fc, tr, tc, promotion="Q"):
        nonlocal selected, legal_tgts, last_move, status_msg, status_warn
        snap = _snapshot()
        # 評価値の変化でコメント種別を決定
        piece_before = g.board[fr][fc] if fr is not None else None
        target_before = g.board[tr][tc] if g.board[tr][tc] else None
        ok, msg = g.move_sq(fr, fc, tr, tc, promotion)
        if ok:
            undo_stack.append(snap)
            if len(undo_stack) > 60: undo_stack.pop(0)
            last_move = [(fr, fc), (tr, tc)]
            selected  = None
            legal_tgts = []
            status_msg  = f"✔ {msg}"
            status_warn = False
            # ── コメンタートリガー ──────────────────────────
            if commentator:
                in_chk = g.in_check(g.turn)
                is_capture = target_before is not None
                is_promo = promotion and piece_before and piece_before[1] == "P"
                if g.game_over:
                    commentator.trigger("ゲームセット", f"結果: {g.result}")
                elif in_chk:
                    commentator.trigger("チェック", f"{msg} — チェック！")
                elif is_promo:
                    commentator.trigger("ポーンがプロモーション", f"{msg}")
                elif is_capture:
                    commentator.trigger("駒を取った", f"{msg}")
                else:
                    if _rnd_chess.random() < 0.3:
                        commentator.trigger("指し手", f"{msg} ({len(g.move_history)}手目)")
            # ────────────────────────────────────────────────
            if g.game_over:
                status_msg  = f"🏆 {g.result}"
                status_warn = True
        else:
            status_msg  = f"✖ {msg}"
            status_warn = True
        return ok

    def _draw_telop_chess():
        """ペルソナのテロップを最下行に表示（チェス版）"""
        if commentator is None:
            return
        h, w_max = stdscr.getmaxyx()
        lines = commentator.get_lines()
        if not lines:
            return
        text = lines[-1]
        try:
            stdscr.addstr(h - 1, 0, f" ♟ {text} ".ljust(w_max - 1),
                          curses.color_pair(_CP_COMMENT) | curses.A_BOLD)
        except curses.error:
            pass

    def _redraw():
        stdscr.erase()
        _draw_title()
        _draw_board()
        _draw_panel()
        _draw_status(status_msg, status_warn)
        _draw_telop_chess()
        stdscr.refresh()

    # ── メインループ ──────────────────────────────────────────
    import random as _rnd_chess
    _diff_labels_chess = {"easy": "Easy", "middle": "Middle", "hard": "Hard", "very_hard": "Very Hard"}
    _chess_ai_thread: threading.Thread | None = None
    _chess_ai_result: list = []

    def _chess_ai_think_bg():
        try:
            mv = ai.choose_move(g)
            _chess_ai_result.clear()
            if mv:
                _chess_ai_result.append(mv)
        except Exception:
            _chess_ai_result.clear()

    while True:
        # AI手番の処理（バックグラウンドスレッド）
        if ai and not g.game_over and g.turn == ai.color and not promo_pending:
            if _chess_ai_thread is None or not _chess_ai_thread.is_alive():
                if _chess_ai_result:
                    # 思考完了 → 着手
                    ai_move = _chess_ai_result[0]
                    _chess_ai_result.clear()
                    _chess_ai_thread = None
                    fr, fc, tr, tc = ai_move
                    snap = _snapshot()
                    ok, msg = g.move_sq(fr, fc, tr, tc)
                    if ok:
                        undo_stack.append(snap)
                        if len(undo_stack) > 60: undo_stack.pop(0)
                        last_move = [(fr, fc), (tr, tc)]
                        selected  = None
                        legal_tgts = []
                        status_msg = f"AI [{_diff_labels_chess.get(ai.difficulty,'')}]: {msg}"
                        status_warn = False
                        if g.game_over:
                            status_msg  = f"🏆 {g.result}"
                            status_warn = True
                        if commentator:
                            in_chk = g.in_check(g.turn)
                            if g.game_over:
                                commentator.trigger("AIが勝利", f"結果: {g.result}")
                            elif in_chk:
                                commentator.trigger("AIがチェック", f"AI: {msg}")
                            elif _rnd_chess.random() < 0.4:
                                commentator.trigger("AIの指し手", f"AI: {msg}")
                else:
                    # 思考スレッド起動
                    _chess_ai_result.clear()
                    status_msg = f"AI [{_diff_labels_chess.get(ai.difficulty,'')}] 思考中..."
                    status_warn = False
                    _chess_ai_thread = threading.Thread(target=_chess_ai_think_bg, daemon=True)
                    _chess_ai_thread.start()
            _redraw()
            stdscr.timeout(80)
            stdscr.getch()
            continue

        _redraw()

        # プロモーション待ち状態のとき専用ループ
        if promo_pending:
            fr, fc, tr, tc = promo_pending
            zones = _draw_promotion_popup(g.board[tr][tc][0] if g.board[tr][tc] else
                                          ("w" if (tr == 0) else "b"))
            # ポップアップ中だけ入力を待つ
            while True:
                key = stdscr.getch()
                if key in (ord('q'), ord('Q')): prom = "Q"; break
                if key in (ord('r'), ord('R')): prom = "R"; break
                if key in (ord('b'), ord('B')): prom = "B"; break
                if key in (ord('n'), ord('N')): prom = "N"; break
                if key == curses.KEY_MOUSE:
                    try:
                        _, mx, my, _, bstate = curses.getmouse()
                        if bstate & curses.BUTTON1_CLICKED or bstate & curses.BUTTON1_PRESSED:
                            for ptype, zy, zx0, zx1 in zones:
                                if my == zy and zx0 <= mx < zx1:
                                    prom = ptype
                                    break
                            else:
                                continue
                            break
                    except curses.error:
                        continue
            # promotion確定: ターンを一時的に修正して打つ
            # g.board[tr][tc] はすでに駒があるかもしれないので promo_pending 時のボードを使う
            # 実際には promo_pending 時点でまだ move_sq を呼んでいないので普通に呼ぶ
            promo_pending = None
            _do_move(fr, fc, tr, tc, prom)
            _redraw()
            continue

        key = stdscr.getch()

        if key == curses.KEY_MOUSE:
            try:
                _, mx, my, _, bstate = curses.getmouse()
            except curses.error:
                continue

            if not (bstate & curses.BUTTON1_CLICKED or bstate & curses.BUTTON1_PRESSED):
                continue

            # ボタン判定
            action = _btn_at(my, mx)
            if action == "quit":
                return "チェス終了"
            if action == "new":
                g.reset()
                undo_stack.clear()
                selected   = None
                legal_tgts = []
                last_move  = []
                _diff_labels = {"easy": "Easy", "middle": "Middle", "hard": "Hard", "very_hard": "Very Hard"}
                ai_str = f"[AI:{_diff_labels.get(ai.difficulty,'')}] " if ai else ""
                status_msg  = f"新しいゲームを開始しました {ai_str}"
                status_warn = False
                continue
            if action == "undo":
                if undo_stack:
                    _restore(undo_stack.pop())
                    selected   = None
                    legal_tgts = []
                    last_move  = []
                    status_msg  = "1手戻しました"
                    status_warn = False
                else:
                    status_msg  = "戻せる手がありません"
                    status_warn = True
                continue

            # マス判定
            sq = _screen_to_sq(my, mx)
            if sq is None:
                continue

            r, c = sq

            if g.game_over:
                status_msg  = f"ゲーム終了: {g.result}  (New で新ゲーム)"
                status_warn = True
                continue

            if selected is None:
                # 駒を選択
                piece = g.board[r][c]
                # AIモード: 相手の駒は動かせない
                if ai and piece and piece[0] == ai.color:
                    status_msg  = f"それはAIの駒です"
                    status_warn = True
                elif piece and piece[0] == g.turn:
                    targets = g.legal_targets(r, c)
                    if targets:
                        selected   = (r, c)
                        legal_tgts = targets
                        pname = {"K":"キング","Q":"クイーン","R":"ルーク",
                                  "B":"ビショップ","N":"ナイト","P":"ポーン"}.get(piece[1], piece[1])
                        status_msg  = f"選択: {g.sq_name(r,c)} ({pname})  — 移動先をクリック"
                        status_warn = False
                    else:
                        status_msg  = f"{g.sq_name(r,c)} の駒は動けません"
                        status_warn = True
                elif piece and piece[0] != g.turn:
                    status_msg  = f"{'白' if g.turn=='w' else '黒'}の手番です"
                    status_warn = True
                else:
                    status_msg  = "その位置に駒がありません"
                    status_warn = True
            else:
                fr, fc = selected
                if (r, c) == selected:
                    # 同じマスをクリック → 選択解除
                    selected   = None
                    legal_tgts = []
                    status_msg  = "選択を解除しました"
                    status_warn = False
                elif (r, c) in legal_tgts:
                    # 合法手マスへ移動
                    piece = g.board[fr][fc]
                    # プロモーション?
                    if piece and piece[1] == "P" and (r == 0 or r == 7):
                        promo_pending = (fr, fc, r, c)
                        status_msg  = "プロモーション駒をクリックして選択"
                        status_warn = False
                    else:
                        _do_move(fr, fc, r, c)
                elif g.board[r][c] and g.board[r][c][0] == g.turn:
                    # 別の自駒をクリック → 選択し直し
                    targets = g.legal_targets(r, c)
                    if targets:
                        selected   = (r, c)
                        legal_tgts = targets
                        pname = {"K":"キング","Q":"クイーン","R":"ルーク",
                                  "B":"ビショップ","N":"ナイト","P":"ポーン"}.get(g.board[r][c][1], "")
                        status_msg  = f"選択変更: {g.sq_name(r,c)} ({pname})"
                        status_warn = False
                    else:
                        selected = None; legal_tgts = []
                else:
                    # 合法手外をクリック → 選択解除
                    selected   = None
                    legal_tgts = []
                    status_msg  = "合法手ではありません。別の駒を選んでください"
                    status_warn = True

        elif key in (ord('q'), ord('Q'), 27):   # q / ESC
            return "チェス終了"
        elif key in (ord('n'), ord('N')):
            g.reset()
            undo_stack.clear()
            selected = None; legal_tgts = []; last_move = []
            _diff_labels = {"easy": "Easy", "middle": "Middle", "hard": "Hard", "very_hard": "Very Hard"}
            ai_str = f"[AI:{_diff_labels.get(ai.difficulty,'')}] " if ai else ""
            status_msg = f"新しいゲームを開始しました {ai_str}"; status_warn = False
        elif key in (ord('u'), ord('U')):
            if undo_stack:
                _restore(undo_stack.pop())
                selected = None; legal_tgts = []; last_move = []
                status_msg = "1手戻しました"; status_warn = False
            else:
                status_msg = "戻せる手がありません"; status_warn = True


_CHESS_GAME: "ChessEngine | None" = None

def handle_chess(arg: str, persona: dict | None = None) -> str:
    """チェスゲームのエントリポイント。/chess [easy|middle|hard|very_hard] で起動。"""
    global _CHESS_GAME
    arg = arg.strip().lower()

    # 難易度キーワードを解析
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

    if _CHESS_GAME is None or "new" in arg or ai_difficulty is not None:
        _CHESS_GAME = ChessEngine(use_unicode=True)

    ai = ChessAI(difficulty=ai_difficulty, color="b") if ai_difficulty else None
    # ペルソナコメンタータ生成
    _persona = persona or {"name": "プラトン", "style": "格調高い哲学者口調", "first_person": "私"}
    commentator = GameCommentator(_persona, game_kind="チェス")

    try:
        result = curses.wrapper(_chess_curses_main, _CHESS_GAME, ai, commentator)
    except Exception as e:
        return f"\033[31mチェス起動エラー: {e}\033[0m"
    return f"\033[32m{result or 'チェスを終了しました'}\033[0m"

