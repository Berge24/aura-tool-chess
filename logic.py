"""
Logica degli Scacchi per AURA — gioca contro AURA.

Contiene:
  - Motore di scacchi completo (rappresentazione 0x88):
      * generazione mosse legali (incl. arrocco, en passant, promozione)
      * make/undo con ripristino completo dello stato
      * rilevamento scacco / scacco matto / stallo / materiale insufficiente
      * import/export FEN
  - IA avversaria: minimax con potatura alfa-beta + tabelle posizionali
      * tre livelli di difficolta: facile / medio / difficile
  - Persistenza statistiche in ~/.aura/chess_stats.json
  - Contratto AURA: describe_chess(), run_chess(user_input)

Nessuna dipendenza esterna: solo libreria standard. Il pannello (panel.py)
disegna la scacchiera e chiama questo modulo per regole e mosse dell'IA.

Rappresentazione 0x88:
  - 128 caselle; una casella e' valida se (idx & 0x88) == 0
  - indice = rank * 16 + file, con rank 0 = traversa 1 (lato Bianco),
    file 0 = colonna a
  - pezzi: maiuscole = Bianco (PNBRQK), minuscole = Nero (pnbrqk),
    '.' = casella vuota
"""

from __future__ import annotations

import json
import random
from datetime import datetime
from pathlib import Path

# ============================================================
# Costanti
# ============================================================

EMPTY = "."

WHITE = "w"
BLACK = "b"

START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"

# Offset di movimento (0x88)
KNIGHT_OFFSETS = (33, 31, 18, 14, -33, -31, -18, -14)
KING_OFFSETS = (16, -16, 1, -1, 17, 15, -17, -15)
BISHOP_DIRS = (17, 15, -17, -15)
ROOK_DIRS = (16, -16, 1, -1)
QUEEN_DIRS = BISHOP_DIRS + ROOK_DIRS

# Valore dei pezzi (centesimi di pedone)
PIECE_VALUE = {"P": 100, "N": 320, "B": 330, "R": 500, "Q": 900, "K": 20000}

# Glifi Unicode (per la UI e per i log)
GLYPHS = {
    "K": "\u2654", "Q": "\u2655", "R": "\u2656", "B": "\u2657",
    "N": "\u2658", "P": "\u2659",
    "k": "\u265A", "q": "\u265B", "r": "\u265C", "b": "\u265D",
    "n": "\u265E", "p": "\u265F",
}

# Tabelle posizionali (punto di vista del Bianco; per il Nero si specchia
# verticalmente). Indici 0..63 in stile a1=0 ... h8=63 (rank-major).
_PST_PAWN = [
     0,  0,  0,  0,  0,  0,  0,  0,
     5, 10, 10,-20,-20, 10, 10,  5,
     5, -5,-10,  0,  0,-10, -5,  5,
     0,  0,  0, 20, 20,  0,  0,  0,
     5,  5, 10, 25, 25, 10,  5,  5,
    10, 10, 20, 30, 30, 20, 10, 10,
    50, 50, 50, 50, 50, 50, 50, 50,
     0,  0,  0,  0,  0,  0,  0,  0,
]
_PST_KNIGHT = [
    -50,-40,-30,-30,-30,-30,-40,-50,
    -40,-20,  0,  5,  5,  0,-20,-40,
    -30,  5, 10, 15, 15, 10,  5,-30,
    -30,  0, 15, 20, 20, 15,  0,-30,
    -30,  5, 15, 20, 20, 15,  5,-30,
    -30,  0, 10, 15, 15, 10,  0,-30,
    -40,-20,  0,  0,  0,  0,-20,-40,
    -50,-40,-30,-30,-30,-30,-40,-50,
]
_PST_BISHOP = [
    -20,-10,-10,-10,-10,-10,-10,-20,
    -10,  5,  0,  0,  0,  0,  5,-10,
    -10, 10, 10, 10, 10, 10, 10,-10,
    -10,  0, 10, 10, 10, 10,  0,-10,
    -10,  5,  5, 10, 10,  5,  5,-10,
    -10,  0,  5, 10, 10,  5,  0,-10,
    -10,  0,  0,  0,  0,  0,  0,-10,
    -20,-10,-10,-10,-10,-10,-10,-20,
]
_PST_ROOK = [
      0,  0,  5, 10, 10,  5,  0,  0,
     -5,  0,  0,  0,  0,  0,  0, -5,
     -5,  0,  0,  0,  0,  0,  0, -5,
     -5,  0,  0,  0,  0,  0,  0, -5,
     -5,  0,  0,  0,  0,  0,  0, -5,
     -5,  0,  0,  0,  0,  0,  0, -5,
      5, 10, 10, 10, 10, 10, 10,  5,
      0,  0,  0,  0,  0,  0,  0,  0,
]
_PST_QUEEN = [
    -20,-10,-10, -5, -5,-10,-10,-20,
    -10,  0,  5,  0,  0,  0,  0,-10,
    -10,  5,  5,  5,  5,  5,  0,-10,
      0,  0,  5,  5,  5,  5,  0, -5,
     -5,  0,  5,  5,  5,  5,  0, -5,
    -10,  0,  5,  5,  5,  5,  0,-10,
    -10,  0,  0,  0,  0,  0,  0,-10,
    -20,-10,-10, -5, -5,-10,-10,-20,
]
_PST_KING = [
     20, 30, 10,  0,  0, 10, 30, 20,
     20, 20,  0,  0,  0,  0, 20, 20,
    -10,-20,-20,-20,-20,-20,-20,-10,
    -20,-30,-30,-40,-40,-30,-30,-20,
    -30,-40,-40,-50,-50,-40,-40,-30,
    -30,-40,-40,-50,-50,-40,-40,-30,
    -30,-40,-40,-50,-50,-40,-40,-30,
    -30,-40,-40,-50,-50,-40,-40,-30,
]
_PST = {
    "P": _PST_PAWN, "N": _PST_KNIGHT, "B": _PST_BISHOP,
    "R": _PST_ROOK, "Q": _PST_QUEEN, "K": _PST_KING,
}


# ============================================================
# Helper 0x88
# ============================================================

def sq(file: int, rank: int) -> int:
    return rank * 16 + file


def file_of(s: int) -> int:
    return s & 7


def rank_of(s: int) -> int:
    return s >> 4


def on_board(s: int) -> bool:
    return (s & 0x88) == 0


def sq_to_algebraic(s: int) -> str:
    return "abcdefgh"[file_of(s)] + str(rank_of(s) + 1)


def algebraic_to_sq(text: str) -> int:
    text = text.strip().lower()
    f = "abcdefgh".index(text[0])
    r = int(text[1]) - 1
    return sq(f, r)


def _sq64(s: int) -> int:
    """0x88 -> indice 0..63 (rank-major) per le tabelle posizionali."""
    return rank_of(s) * 8 + file_of(s)


def is_white_piece(p: str) -> bool:
    return p != EMPTY and p.isupper()


def is_black_piece(p: str) -> bool:
    return p != EMPTY and p.islower()


def piece_color(p: str) -> str | None:
    if p == EMPTY:
        return None
    return WHITE if p.isupper() else BLACK


# ============================================================
# Modello mossa
# ============================================================

class Move:
    """Una mossa. `flag` puo' essere:
       '' normale, 'c' arrocco corto, 'C' arrocco lungo,
       'e' presa en passant, 'd' doppio passo pedone,
       'p' promozione (con self.promo = pezzo, es. 'Q')."""

    __slots__ = ("frm", "to", "promo", "flag")

    def __init__(self, frm: int, to: int, promo: str = "", flag: str = ""):
        self.frm = frm
        self.to = to
        self.promo = promo
        self.flag = flag

    def uci(self) -> str:
        s = sq_to_algebraic(self.frm) + sq_to_algebraic(self.to)
        if self.promo:
            s += self.promo.lower()
        return s

    def __eq__(self, other) -> bool:
        return (
            isinstance(other, Move)
            and self.frm == other.frm
            and self.to == other.to
            and self.promo == other.promo
        )

    def __hash__(self) -> int:
        return hash((self.frm, self.to, self.promo))

    def __repr__(self) -> str:
        return f"Move({self.uci()})"


# ============================================================
# Scacchiera
# ============================================================

class Board:
    def __init__(self, fen: str = START_FEN):
        self.board: list[str] = [EMPTY] * 128
        self.turn: str = WHITE
        # diritti di arrocco: set di 'K','Q','k','q'
        self.castling: set[str] = set()
        self.ep: int | None = None       # casella di presa en passant
        self.halfmove: int = 0           # regola delle 50 mosse
        self.fullmove: int = 1
        self._undo_stack: list = []
        self.set_fen(fen)

    # ---------- FEN ----------

    def set_fen(self, fen: str) -> None:
        self.board = [EMPTY] * 128
        parts = fen.split()
        placement = parts[0]
        ranks = placement.split("/")  # rank 8 .. rank 1
        for fen_rank_index, row in enumerate(ranks):
            rank = 7 - fen_rank_index
            file = 0
            for ch in row:
                if ch.isdigit():
                    file += int(ch)
                else:
                    self.board[sq(file, rank)] = ch
                    file += 1
        self.turn = parts[1] if len(parts) > 1 else WHITE
        self.castling = set()
        if len(parts) > 2 and parts[2] != "-":
            for c in parts[2]:
                if c in "KQkq":
                    self.castling.add(c)
        self.ep = None
        if len(parts) > 3 and parts[3] != "-":
            self.ep = algebraic_to_sq(parts[3])
        self.halfmove = int(parts[4]) if len(parts) > 4 else 0
        self.fullmove = int(parts[5]) if len(parts) > 5 else 1

    def fen(self) -> str:
        rows = []
        for rank in range(7, -1, -1):
            row = ""
            empty = 0
            for file in range(8):
                p = self.board[sq(file, rank)]
                if p == EMPTY:
                    empty += 1
                else:
                    if empty:
                        row += str(empty)
                        empty = 0
                    row += p
            if empty:
                row += str(empty)
            rows.append(row)
        placement = "/".join(rows)
        castle = "".join(c for c in "KQkq" if c in self.castling) or "-"
        ep = sq_to_algebraic(self.ep) if self.ep is not None else "-"
        return f"{placement} {self.turn} {castle} {ep} {self.halfmove} {self.fullmove}"

    # ---------- Utility ----------

    def king_square(self, color: str) -> int | None:
        target = "K" if color == WHITE else "k"
        for s in range(128):
            if on_board(s) and self.board[s] == target:
                return s
        return None

    def is_attacked(self, target: int, by_color: str) -> bool:
        """True se `target` e' attaccata da un pezzo di colore `by_color`."""
        # Pedoni
        if by_color == WHITE:
            for off in (-17, -15):   # un pedone bianco attacca verso l'alto;
                src = target + off   # quindi parte da una casella sotto target
                if on_board(src) and self.board[src] == "P":
                    return True
        else:
            for off in (17, 15):
                src = target + off
                if on_board(src) and self.board[src] == "p":
                    return True
        # Cavalli
        kn = "N" if by_color == WHITE else "n"
        for off in KNIGHT_OFFSETS:
            src = target + off
            if on_board(src) and self.board[src] == kn:
                return True
        # Re
        kg = "K" if by_color == WHITE else "k"
        for off in KING_OFFSETS:
            src = target + off
            if on_board(src) and self.board[src] == kg:
                return True
        # Pezzi sulle diagonali (alfiere / donna)
        diag = ("B", "Q") if by_color == WHITE else ("b", "q")
        for d in BISHOP_DIRS:
            src = target + d
            while on_board(src):
                p = self.board[src]
                if p != EMPTY:
                    if p in diag:
                        return True
                    break
                src += d
        # Pezzi su righe/colonne (torre / donna)
        line = ("R", "Q") if by_color == WHITE else ("r", "q")
        for d in ROOK_DIRS:
            src = target + d
            while on_board(src):
                p = self.board[src]
                if p != EMPTY:
                    if p in line:
                        return True
                    break
                src += d
        return False

    def in_check(self, color: str | None = None) -> bool:
        color = color or self.turn
        ks = self.king_square(color)
        if ks is None:
            return False
        enemy = BLACK if color == WHITE else WHITE
        return self.is_attacked(ks, enemy)

    # ---------- Generazione mosse ----------

    def _pseudo_legal_moves(self) -> list[Move]:
        moves: list[Move] = []
        color = self.turn
        own = is_white_piece if color == WHITE else is_black_piece
        enemy = is_black_piece if color == WHITE else is_white_piece

        for s in range(128):
            if not on_board(s):
                continue
            p = self.board[s]
            if p == EMPTY or not own(p):
                continue
            pu = p.upper()

            if pu == "P":
                self._gen_pawn(s, color, enemy, moves)
            elif pu == "N":
                for off in KNIGHT_OFFSETS:
                    t = s + off
                    if on_board(t) and not own(self.board[t]):
                        moves.append(Move(s, t))
            elif pu == "K":
                for off in KING_OFFSETS:
                    t = s + off
                    if on_board(t) and not own(self.board[t]):
                        moves.append(Move(s, t))
                self._gen_castling(s, color, moves)
            else:
                dirs = (
                    BISHOP_DIRS if pu == "B"
                    else ROOK_DIRS if pu == "R"
                    else QUEEN_DIRS
                )
                for d in dirs:
                    t = s + d
                    while on_board(t):
                        tp = self.board[t]
                        if tp == EMPTY:
                            moves.append(Move(s, t))
                        else:
                            if enemy(tp):
                                moves.append(Move(s, t))
                            break
                        t += d
        return moves

    def _gen_pawn(self, s, color, enemy, moves):
        if color == WHITE:
            fwd, start_rank, promo_rank = 16, 1, 7
        else:
            fwd, start_rank, promo_rank = -16, 6, 0
        rk = rank_of(s)

        # avanzamento di una
        one = s + fwd
        if on_board(one) and self.board[one] == EMPTY:
            if rank_of(one) == promo_rank:
                for pr in ("Q", "R", "B", "N"):
                    moves.append(Move(s, one, promo=pr, flag="p"))
            else:
                moves.append(Move(s, one))
                # avanzamento di due
                if rk == start_rank:
                    two = s + 2 * fwd
                    if on_board(two) and self.board[two] == EMPTY:
                        moves.append(Move(s, two, flag="d"))

        # catture (incl. en passant)
        for cap_off in (fwd + 1, fwd - 1):
            t = s + cap_off
            if not on_board(t):
                continue
            tp = self.board[t]
            if tp != EMPTY and enemy(tp):
                if rank_of(t) == promo_rank:
                    for pr in ("Q", "R", "B", "N"):
                        moves.append(Move(s, t, promo=pr, flag="p"))
                else:
                    moves.append(Move(s, t))
            elif self.ep is not None and t == self.ep:
                moves.append(Move(s, t, flag="e"))

    def _gen_castling(self, s, color, moves):
        if self.in_check(color):
            return
        enemy = BLACK if color == WHITE else WHITE
        if color == WHITE:
            ks, qs = "K", "Q"
            e1, f1, g1, d1, c1, b1 = sq(4, 0), sq(5, 0), sq(6, 0), sq(3, 0), sq(2, 0), sq(1, 0)
            a1, h1 = sq(0, 0), sq(7, 0)
            rook = "R"
        else:
            ks, qs = "k", "q"
            e1, f1, g1, d1, c1, b1 = sq(4, 7), sq(5, 7), sq(6, 7), sq(3, 7), sq(2, 7), sq(1, 7)
            a1, h1 = sq(0, 7), sq(7, 7)
            rook = "r"

        # lato di re
        if ks in self.castling and self.board[h1] == rook:
            if self.board[f1] == EMPTY and self.board[g1] == EMPTY:
                if (not self.is_attacked(f1, enemy)
                        and not self.is_attacked(g1, enemy)):
                    moves.append(Move(e1, g1, flag="c"))
        # lato di donna
        if qs in self.castling and self.board[a1] == rook:
            if (self.board[d1] == EMPTY and self.board[c1] == EMPTY
                    and self.board[b1] == EMPTY):
                if (not self.is_attacked(d1, enemy)
                        and not self.is_attacked(c1, enemy)):
                    moves.append(Move(e1, c1, flag="C"))

    def legal_moves(self) -> list[Move]:
        color = self.turn
        result = []
        for m in self._pseudo_legal_moves():
            self.make_move(m)
            if not self.in_check(color):
                result.append(m)
            self.undo_move()
        return result

    # ---------- make / undo ----------

    def make_move(self, m: Move) -> None:
        # snapshot per undo
        undo = {
            "frm": m.frm, "to": m.to, "flag": m.flag, "promo": m.promo,
            "piece": self.board[m.frm],
            "captured": self.board[m.to],
            "captured_sq": m.to,
            "castling": set(self.castling),
            "ep": self.ep,
            "halfmove": self.halfmove,
            "turn": self.turn,
        }

        piece = self.board[m.frm]
        color = self.turn
        is_pawn = piece.upper() == "P"
        is_capture = self.board[m.to] != EMPTY

        # reset ep di default
        new_ep = None

        # muovi il pezzo
        self.board[m.to] = piece
        self.board[m.frm] = EMPTY

        if m.flag == "d":
            # imposta casella en passant dietro al pedone
            new_ep = m.to - 16 if color == WHITE else m.to + 16
        elif m.flag == "e":
            # rimuovi il pedone catturato (dietro la casella di arrivo)
            cap_sq = m.to - 16 if color == WHITE else m.to + 16
            undo["captured"] = self.board[cap_sq]
            undo["captured_sq"] = cap_sq
            self.board[cap_sq] = EMPTY
            is_capture = True
        elif m.flag == "p":
            promo = (m.promo or "Q")
            self.board[m.to] = promo if color == WHITE else promo.lower()
        elif m.flag == "c":
            # arrocco corto: muovi la torre
            if color == WHITE:
                self.board[sq(5, 0)] = "R"; self.board[sq(7, 0)] = EMPTY
            else:
                self.board[sq(5, 7)] = "r"; self.board[sq(7, 7)] = EMPTY
        elif m.flag == "C":
            # arrocco lungo
            if color == WHITE:
                self.board[sq(3, 0)] = "R"; self.board[sq(0, 0)] = EMPTY
            else:
                self.board[sq(3, 7)] = "r"; self.board[sq(0, 7)] = EMPTY

        # aggiorna diritti di arrocco
        self._update_castling_rights(m.frm, m.to, piece)

        self.ep = new_ep

        # halfmove clock
        if is_pawn or is_capture:
            self.halfmove = 0
        else:
            self.halfmove += 1

        if color == BLACK:
            self.fullmove += 1
        self.turn = BLACK if color == WHITE else WHITE

        self._undo_stack.append(undo)

    def _update_castling_rights(self, frm, to, piece):
        # se si muove il re, perdi entrambi i diritti
        if piece == "K":
            self.castling.discard("K"); self.castling.discard("Q")
        elif piece == "k":
            self.castling.discard("k"); self.castling.discard("q")
        # se si muove (o viene catturata) una torre d'angolo
        a1, h1, a8, h8 = sq(0, 0), sq(7, 0), sq(0, 7), sq(7, 7)
        for s in (frm, to):
            if s == h1:
                self.castling.discard("K")
            elif s == a1:
                self.castling.discard("Q")
            elif s == h8:
                self.castling.discard("k")
            elif s == a8:
                self.castling.discard("q")

    def undo_move(self) -> None:
        if not self._undo_stack:
            return
        u = self._undo_stack.pop()
        color = u["turn"]
        frm, to, flag = u["frm"], u["to"], u["flag"]

        # rimetti il pezzo che ha mosso
        self.board[frm] = u["piece"]
        self.board[to] = EMPTY

        # ripristina catture (en passant: la casella catturata != to)
        if u["captured"] != EMPTY or flag == "e":
            self.board[u["captured_sq"]] = u["captured"]

        if flag == "c":
            if color == WHITE:
                self.board[sq(7, 0)] = "R"; self.board[sq(5, 0)] = EMPTY
            else:
                self.board[sq(7, 7)] = "r"; self.board[sq(5, 7)] = EMPTY
        elif flag == "C":
            if color == WHITE:
                self.board[sq(0, 0)] = "R"; self.board[sq(3, 0)] = EMPTY
            else:
                self.board[sq(0, 7)] = "r"; self.board[sq(3, 7)] = EMPTY

        self.castling = u["castling"]
        self.ep = u["ep"]
        self.halfmove = u["halfmove"]
        self.turn = color
        if color == BLACK:
            self.fullmove -= 1

    # ---------- Stato finale ----------

    def is_checkmate(self) -> bool:
        return self.in_check() and not self.legal_moves()

    def is_stalemate(self) -> bool:
        return not self.in_check() and not self.legal_moves()

    def insufficient_material(self) -> bool:
        pieces = [self.board[s] for s in range(128)
                  if on_board(s) and self.board[s] != EMPTY]
        non_king = [p for p in pieces if p.upper() != "K"]
        if not non_king:
            return True  # solo i due re
        if len(non_king) == 1 and non_king[0].upper() in ("B", "N"):
            return True  # re + alfiere/cavallo vs re
        if (len(non_king) == 2
                and all(p.upper() == "B" for p in non_king)):
            # due alfieri: insufficiente solo se sulle stesse case (raro);
            # approssimazione prudente: non lo dichiariamo patta automatica
            return False
        return False

    def result(self) -> str | None:
        """Ritorna 'white', 'black', 'draw' o None se la partita continua."""
        if not self.legal_moves():
            if self.in_check():
                return BLACK if self.turn == WHITE else WHITE  # chi muove e' matto
            return "draw"  # stallo
        if self.halfmove >= 100:
            return "draw"  # 50 mosse
        if self.insufficient_material():
            return "draw"
        return None


# ============================================================
# Notazione SAN (semplificata) per i log
# ============================================================

def move_to_san(board: Board, move: Move) -> str:
    if move.flag == "c":
        san = "O-O"
    elif move.flag == "C":
        san = "O-O-O"
    else:
        piece = board.board[move.frm]
        pu = piece.upper()
        is_capture = board.board[move.to] != EMPTY or move.flag == "e"
        dest = sq_to_algebraic(move.to)
        if pu == "P":
            san = (sq_to_algebraic(move.frm)[0] + "x" + dest) if is_capture else dest
            if move.flag == "p":
                san += "=" + (move.promo or "Q")
        else:
            san = pu + ("x" if is_capture else "") + dest
    # suffisso scacco / matto
    board.make_move(move)
    if board.is_checkmate():
        san += "#"
    elif board.in_check():
        san += "+"
    board.undo_move()
    return san


# ============================================================
# IA: valutazione + minimax con alfa-beta
# ============================================================

def evaluate(board: Board) -> int:
    """Punteggio dal punto di vista del Bianco (positivo = Bianco meglio)."""
    score = 0
    for s in range(128):
        if not on_board(s):
            continue
        p = board.board[s]
        if p == EMPTY:
            continue
        pu = p.upper()
        val = PIECE_VALUE[pu]
        idx = _sq64(s)
        pst = _PST[pu]
        if p.isupper():
            score += val + pst[idx]
        else:
            score -= val + pst[idx ^ 56]  # specchio verticale per il Nero
    return score


def _negamax(board: Board, depth: int, alpha: int, beta: int) -> int:
    res = board.result()
    if res is not None:
        if res == "draw":
            return 0
        # matto: chi deve muovere ha perso
        winner = res
        side = WHITE if board.turn == WHITE else BLACK
        # punteggio "lato che muove": se ha perso, molto negativo
        return -100000 - depth if winner != side else 100000 + depth
    if depth == 0:
        sign = 1 if board.turn == WHITE else -1
        return sign * evaluate(board)

    best = -10**9
    moves = _ordered_moves(board)
    for m in moves:
        board.make_move(m)
        val = -_negamax(board, depth - 1, -beta, -alpha)
        board.undo_move()
        if val > best:
            best = val
        if best > alpha:
            alpha = best
        if alpha >= beta:
            break
    return best


def _ordered_moves(board: Board) -> list[Move]:
    """Ordina le mosse: prima le catture (MVV-LVA grezzo) per potare meglio."""
    moves = board.legal_moves()

    def key(m: Move) -> int:
        victim = board.board[m.to]
        if victim != EMPTY:
            return 10 * PIECE_VALUE[victim.upper()] - PIECE_VALUE[board.board[m.frm].upper()]
        if m.flag == "e":
            return 900
        if m.flag == "p":
            return 800
        return 0

    return sorted(moves, key=key, reverse=True)


def select_ai_move(board: Board, difficulty: str = "medio",
                   rng: random.Random | None = None) -> Move | None:
    """Sceglie una mossa per il lato al tratto.

    difficulty:
      - 'facile'   : per lo piu' casuale, ma evita di regalare materiale
      - 'medio'    : minimax profondita' 2
      - 'difficile': minimax profondita' 3
    """
    r = rng or random.Random()
    moves = board.legal_moves()
    if not moves:
        return None

    if difficulty == "facile":
        # 35% mossa casuale; altrimenti depth 1 con un pizzico di rumore
        if r.random() < 0.35:
            return r.choice(moves)
        depth = 1
    elif difficulty == "difficile":
        depth = 3
    else:
        depth = 2

    best_val = -10**9
    best_moves: list[Move] = []
    alpha, beta = -10**9, 10**9
    for m in _ordered_moves(board):
        board.make_move(m)
        val = -_negamax(board, depth - 1, -beta, -alpha)
        board.undo_move()
        if val > best_val:
            best_val = val
            best_moves = [m]
        elif val == best_val:
            best_moves.append(m)
        if best_val > alpha:
            alpha = best_val
    return r.choice(best_moves) if best_moves else r.choice(moves)


# ============================================================
# Persistenza statistiche
# ============================================================

STATS_FILE = Path.home() / ".aura" / "chess_stats.json"


def _default_stats() -> dict:
    return {
        "wins": 0,
        "losses": 0,
        "draws": 0,
        "last_played": None,
        "history": [],  # {"result", "difficulty", "color", "moves", "date"}
    }


def load_stats() -> dict:
    try:
        if STATS_FILE.is_file():
            data = json.loads(STATS_FILE.read_text(encoding="utf-8"))
            base = _default_stats()
            base.update(data)
            return base
    except Exception:
        pass
    return _default_stats()


def save_stats(stats: dict) -> None:
    try:
        STATS_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATS_FILE.write_text(
            json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        pass


def record_game(result: str, difficulty: str, color: str, moves: int) -> dict:
    """result: 'win' (umano), 'loss' (umano), 'draw'."""
    stats = load_stats()
    if result == "win":
        stats["wins"] = int(stats.get("wins", 0)) + 1
    elif result == "loss":
        stats["losses"] = int(stats.get("losses", 0)) + 1
    else:
        stats["draws"] = int(stats.get("draws", 0)) + 1
    stats["last_played"] = datetime.now().astimezone().isoformat()
    stats.setdefault("history", []).append({
        "result": result,
        "difficulty": difficulty,
        "color": color,
        "moves": moves,
        "date": stats["last_played"],
    })
    stats["history"] = stats["history"][-100:]
    save_stats(stats)
    return stats


# ============================================================
# Contratto AURA
# ============================================================

def describe_chess() -> str:
    return (
        "Scacchi \u2654 \u2014 Gioca contro AURA!\n"
        "Una partita di scacchi completa: arrocco, en passant, promozione,\n"
        "scacco matto e stallo sono tutti gestiti.\n"
        "AURA fa la sua mossa con un motore minimax locale (nessuna rete).\n"
        "Tre livelli: facile, medio, difficile.\n"
        "Apri il pannello, scegli colore e difficolta', e muovi cliccando\n"
        "prima il tuo pezzo e poi la casella di destinazione."
    )


def run_chess(user_input: str) -> str:
    """Risposta testuale a domande sugli scacchi dalla chat."""
    text = (user_input or "").strip().lower()
    stats = load_stats()

    if any(k in text for k in ["regole", "come si gioca", "spiega", "help", "aiuto"]):
        return describe_chess()

    if any(k in text for k in ["stats", "statistiche", "record", "punteggi", "bilancio"]):
        wins = stats.get("wins", 0)
        losses = stats.get("losses", 0)
        draws = stats.get("draws", 0)
        total = wins + losses + draws
        rate = (wins / total * 100) if total > 0 else 0.0
        lines = [
            "\u2654 Statistiche Scacchi (tu vs AURA):",
            f"  \u2022 Vittorie: {wins}",
            f"  \u2022 Sconfitte: {losses}",
            f"  \u2022 Patte: {draws}",
            f"  \u2022 Partite totali: {total}",
            f"  \u2022 Percentuale vittorie: {rate:.0f}%",
        ]
        return "\n".join(lines)

    wins = stats.get("wins", 0)
    losses = stats.get("losses", 0)
    draws = stats.get("draws", 0)
    if wins + losses + draws == 0:
        return (
            describe_chess()
            + "\n\nApri il pannello per la tua prima partita! \u265F"
        )
    return (
        f"\u2654 Scacchi \u2014 bilancio attuale: {wins}V / {losses}S / {draws}P. "
        f"Apri il pannello per giocare una nuova partita contro AURA!"
    )
