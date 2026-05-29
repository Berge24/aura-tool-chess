"""
Pannello UI degli Scacchi per AURA.

Disegna una scacchiera 8x8 cliccabile (glifi Unicode), gestisce la selezione
del pezzo e l'evidenziazione delle mosse legali, e fa giocare AURA con un
motore minimax eseguito su un thread separato (la UI non si blocca mai).

Controlli:
  - Combo difficolta' (facile / medio / difficile)
  - Combo colore del giocatore (Bianco / Nero)
  - Nuova partita, Annulla mossa, Abbandona
  - Header di stato, bilancio materiale, statistiche storiche

Interazione:
  - Click sul tuo pezzo -> selezione + evidenzia destinazioni legali
  - Click su una destinazione legale -> esegui la mossa
  - Promozione del pedone -> piccola finestra di scelta del pezzo

API pubblica: build_chess_panel(window).
"""

from __future__ import annotations

from PySide6.QtCore import (
    Qt, QThread, Signal, QPropertyAnimation, QPoint, QEasingCurve,
)
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox, QFrame, QGridLayout, QHBoxLayout, QInputDialog, QLabel,
    QMessageBox, QPushButton, QTextEdit, QVBoxLayout, QWidget,
)

try:
    from tools.chess import (
        Board, Move, WHITE, BLACK, EMPTY, GLYPHS, PIECE_VALUE,
        sq, file_of, rank_of, on_board, sq_to_algebraic, algebraic_to_sq,
        select_ai_move, move_to_san, record_game, load_stats, piece_color,
    )
except Exception:
    from chess import (
        Board, Move, WHITE, BLACK, EMPTY, GLYPHS, PIECE_VALUE,
        sq, file_of, rank_of, on_board, sq_to_algebraic, algebraic_to_sq,
        select_ai_move, move_to_san, record_game, load_stats, piece_color,
    )


# Colori scacchiera (stile "green board")
LIGHT_SQ = "#eeeed2"
DARK_SQ = "#769656"
SEL_SQ = "#f6f669"          # casella selezionata
LASTMOVE_SQ = "#cdd26a"     # ultima mossa
TARGET_RING = "#d64f4f"     # bordo per catture legali

SQUARE_PX = 58

# Durata dello scivolamento dei pezzi (ms). Piu' alto = piu' lento.
ANIM_MS = 420


# ============================================================
# Worker IA su thread separato
# ============================================================

class ChessAIWorker(QThread):
    """Calcola la mossa dell'IA da una FEN senza bloccare la UI.
    Emette la mossa in formato UCI (es. 'e2e4', 'e7e8q')."""

    move_ready = Signal(str)

    def __init__(self, fen: str, difficulty: str):
        super().__init__()
        self.fen = fen
        self.difficulty = difficulty

    def run(self):
        try:
            b = Board(self.fen)
            mv = select_ai_move(b, self.difficulty)
            self.move_ready.emit(mv.uci() if mv else "")
        except Exception:
            self.move_ready.emit("")


# ============================================================
# Casella della scacchiera
# ============================================================

class SquareButton(QPushButton):
    square_clicked = Signal(int)

    def __init__(self, square_index: int, parent=None):
        super().__init__(parent)
        self.square_index = square_index
        self.setFixedSize(SQUARE_PX, SQUARE_PX)
        self.setFlat(True)
        self.setFocusPolicy(Qt.NoFocus)
        f = QFont("Segoe UI Symbol", 30)
        self.setFont(f)
        self.clicked.connect(lambda: self.square_clicked.emit(self.square_index))

    def render(self, glyph: str, is_light: bool, selected: bool,
               last_move: bool, target_empty: bool, target_capture: bool):
        if selected:
            bg = SEL_SQ
        elif last_move:
            bg = LASTMOVE_SQ
        else:
            bg = LIGHT_SQ if is_light else DARK_SQ

        # pedine: nere scure, bianche chiare con leggero contorno
        text = glyph
        if target_empty and not glyph:
            text = "\u2022"  # punto per destinazione vuota
            color = "#5b7c3a" if is_light else "#3f5a28"
            self.setText(text)
            self.setStyleSheet(
                f"QPushButton {{ background:{bg}; color:{color};"
                f" border:none; font-size:30px; }}"
            )
            return

        border = f"border:3px solid {TARGET_RING};" if target_capture else "border:none;"
        # colore del glifo in base al pezzo
        glyph_color = "#111111"  # i glifi pieni rendono bene scuri su entrambe
        self.setText(text)
        self.setStyleSheet(
            f"QPushButton {{ background:{bg}; color:{glyph_color};"
            f" {border} font-size:34px; }}"
        )


# ============================================================
# Pannello principale
# ============================================================

def build_chess_panel(window):
    card = window.open_tool_card(
        "Scacchi",
        "Gioca una partita contro AURA. Motore locale, nessuna rete.",
        "\u2654",
        "scacchi",
    )

    state = {
        "board": Board(),
        "player_color": WHITE,
        "difficulty": "medio",
        "selected": None,          # casella 0x88 selezionata
        "legal_from_sel": [],      # mosse legali dalla casella selezionata
        "last_move": None,         # (frm, to)
        "game_over": False,
        "player_moves": 0,
        "ai_thinking": False,
        "ai_worker": None,
        "closed": False,
        "recorded": False,
        "animating": False,
        "anim": None,          # QPropertyAnimation in volo
        "floating": None,      # QLabel del pezzo in volo
        "san_history": [],     # mosse in notazione SAN, in ordine di gioco
    }
    squares: dict[int, SquareButton] = {}

    # ---------- Controlli (riga alta) ----------
    controls = QHBoxLayout()

    diff_combo = QComboBox()
    diff_combo.addItems(["Facile", "Medio", "Difficile"])
    diff_combo.setCurrentIndex(1)

    color_combo = QComboBox()
    color_combo.addItems(["Gioco col Bianco", "Gioco col Nero"])

    new_btn = QPushButton("\u21BA  Nuova partita")
    undo_btn = QPushButton("\u21A9  Annulla")
    resign_btn = QPushButton("\U0001F3F3  Abbandona")

    btn_style = (
        "QPushButton { background:#1e293b; color:#e2e8f0; border:1px solid #334155;"
        " border-radius:8px; padding:6px 12px; } QPushButton:hover { background:#334155; }"
    )
    for b in (new_btn, undo_btn, resign_btn):
        b.setStyleSheet(btn_style)
    combo_style = (
        "QComboBox { background:#1e293b; color:#e2e8f0; border:1px solid #334155;"
        " border-radius:8px; padding:5px 10px; }"
    )
    diff_combo.setStyleSheet(combo_style)
    color_combo.setStyleSheet(combo_style)

    controls.addWidget(diff_combo)
    controls.addWidget(color_combo)
    controls.addStretch()
    controls.addWidget(undo_btn)
    controls.addWidget(new_btn)
    controls.addWidget(resign_btn)

    # ---------- Header di stato ----------
    status = QLabel("")
    status.setAlignment(Qt.AlignCenter)
    status.setStyleSheet("color:#e2e8f0; font-size:15px; font-weight:bold; padding:4px;")

    material = QLabel("")
    material.setAlignment(Qt.AlignCenter)
    material.setStyleSheet("color:#94a3b8; font-size:12px;")

    # ---------- Scacchiera ----------
    board_frame = QFrame()
    board_frame.setStyleSheet("QFrame { background:#312e2b; border-radius:10px; padding:10px; }")
    board_outer = QVBoxLayout(board_frame)
    board_grid_widget = QWidget()
    board_grid = QGridLayout(board_grid_widget)
    board_grid.setSpacing(0)
    board_grid.setContentsMargins(0, 0, 0, 0)
    board_outer.addWidget(board_grid_widget, alignment=Qt.AlignCenter)

    # ---------- Registro mosse (dentro il pannello: la chat non scorre) ----------
    moves_log = QTextEdit()
    moves_log.setReadOnly(True)
    moves_log.setFixedHeight(86)
    moves_log.setFont(QFont("Courier New", 11))
    moves_log.setStyleSheet(
        "QTextEdit { background:#0f172a; color:#cbd5e1; border:1px solid #334155;"
        " border-radius:8px; padding:6px; }"
    )

    stats_label = QLabel("")
    stats_label.setAlignment(Qt.AlignCenter)
    stats_label.setStyleSheet("color:#94a3b8; font-size:12px; padding-top:4px;")

    # ---------- Helpers ----------

    def coord_label(text: str) -> QLabel:
        lab = QLabel(text)
        lab.setAlignment(Qt.AlignCenter)
        lab.setFixedSize(SQUARE_PX, 16)
        lab.setStyleSheet("color:#bfc7b3; font-size:11px;")
        return lab

    def display_order():
        """Ritorna (ranks_top_to_bottom, files_left_to_right) per l'orientamento."""
        if state["player_color"] == WHITE:
            ranks = range(7, -1, -1)
            files = range(0, 8)
        else:
            ranks = range(0, 8)
            files = range(7, -1, -1)
        return list(ranks), list(files)

    def build_board_grid():
        # ferma eventuali animazioni in corso
        _cancel_animation()
        # svuota la griglia
        while board_grid.count():
            item = board_grid.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
                w.deleteLater()
        squares.clear()

        ranks, files = display_order()

        # etichette colonne in alto
        board_grid.addWidget(QLabel(""), 0, 0)
        for ci, f in enumerate(files):
            board_grid.addWidget(coord_label("abcdefgh"[f]), 0, ci + 1)

        for ri, r in enumerate(ranks):
            # etichetta traversa a sinistra
            rk = QLabel(str(r + 1))
            rk.setAlignment(Qt.AlignCenter)
            rk.setFixedSize(18, SQUARE_PX)
            rk.setStyleSheet("color:#bfc7b3; font-size:11px;")
            board_grid.addWidget(rk, ri + 1, 0)
            for ci, f in enumerate(files):
                s = sq(f, r)
                btn = SquareButton(s)
                btn.square_clicked.connect(on_square_click)
                squares[s] = btn
                board_grid.addWidget(btn, ri + 1, ci + 1)
        refresh_board()

    def legal_targets_from(square: int) -> list[Move]:
        if state["game_over"] or state["ai_thinking"]:
            return []
        b = state["board"]
        return [m for m in b.legal_moves() if m.frm == square]

    def refresh_board():
        b = state["board"]
        sel = state["selected"]
        targets = {m.to for m in state["legal_from_sel"]}
        last = state["last_move"]
        for s, btn in squares.items():
            p = b.board[s]
            glyph = GLYPHS.get(p, "") if p != EMPTY else ""
            is_light = (file_of(s) + rank_of(s)) % 2 == 1
            selected = sel == s
            is_last = last is not None and s in last
            is_target_empty = s in targets and p == EMPTY
            is_target_cap = s in targets and p != EMPTY
            btn.render(glyph, is_light, selected, is_last,
                       is_target_empty, is_target_cap)

    def render_move_log():
        h = state["san_history"]
        lines = []
        i = 0
        num = 1
        while i < len(h):
            white = h[i]
            black = h[i + 1] if i + 1 < len(h) else ""
            lines.append(f"{num:>2}. {white:<7} {black}".rstrip())
            i += 2
            num += 1
        moves_log.setPlainText("\n".join(lines))
        sb = moves_log.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _cancel_animation():
        anim = state.get("anim")
        if anim is not None:
            try:
                anim.stop()
            except Exception:
                pass
        flo = state.get("floating")
        if flo is not None:
            try:
                flo.deleteLater()
            except Exception:
                pass
        state["anim"] = None
        state["floating"] = None
        state["animating"] = False

    def _animate_move(move: Move, on_done):
        """Fa scivolare il pezzo dalla casella di partenza a quella d'arrivo,
        poi applica la mossa al motore (in _commit_move)."""
        b = state["board"]
        piece = b.board[move.frm]
        glyph = GLYPHS.get(piece, "")
        src_btn = squares.get(move.frm)
        dst_btn = squares.get(move.to)

        # se le geometrie non sono pronte, applica subito senza animazione
        if (not src_btn or not dst_btn or src_btn.width() == 0
                or src_btn.geometry() == dst_btn.geometry()):
            _commit_move(move, on_done)
            return

        state["animating"] = True
        # nascondi il glifo sulla casella di partenza durante il volo
        src_btn.setText("")

        flo = QLabel(board_grid_widget)
        flo.setAlignment(Qt.AlignCenter)
        flo.setFont(src_btn.font())
        flo.setStyleSheet(
            "QLabel { background: transparent; color:#111111; font-size:34px; }"
        )
        flo.setText(glyph)
        flo.resize(src_btn.size())
        flo.move(src_btn.pos())
        flo.show()
        flo.raise_()
        state["floating"] = flo

        anim = QPropertyAnimation(flo, b"pos")
        anim.setDuration(ANIM_MS)
        anim.setStartValue(QPoint(src_btn.pos()))
        anim.setEndValue(QPoint(dst_btn.pos()))
        anim.setEasingCurve(QEasingCurve.InOutQuad)

        def _finished():
            f = state.get("floating")
            if f is not None:
                try:
                    f.deleteLater()
                except Exception:
                    pass
            state["floating"] = None
            state["anim"] = None
            state["animating"] = False
            _commit_move(move, on_done)

        anim.finished.connect(_finished)
        state["anim"] = anim
        anim.start()

    def _commit_move(move: Move, on_done):
        """Applica la mossa al motore, aggiorna scacchiera e registro."""
        if state["closed"]:
            return
        b = state["board"]
        san = move_to_san(b, move)  # calcolato PRIMA di make_move
        b.make_move(move)
        state["last_move"] = (move.frm, move.to)
        state["san_history"].append(san)
        refresh_board()
        render_move_log()
        if on_done:
            on_done()

    def material_balance() -> str:
        b = state["board"]
        w = bk = 0
        for s in range(128):
            if not on_board(s):
                continue
            p = b.board[s]
            if p == EMPTY or p.upper() == "K":
                continue
            v = PIECE_VALUE[p.upper()]
            if p.isupper():
                w += v
            else:
                bk += v
        diff = (w - bk) // 100
        if diff == 0:
            return "Materiale: pari"
        leader = "Bianco" if diff > 0 else "Nero"
        return f"Materiale: {leader} +{abs(diff)}"

    def refresh_status():
        b = state["board"]
        material.setText(material_balance())
        if state["game_over"]:
            return
        if state["ai_thinking"]:
            status.setText("AURA sta pensando\u2026  \u265F")
            return
        side = "Bianco" if b.turn == WHITE else "Nero"
        your_turn = (b.turn == state["player_color"])
        who = "Tocca a te" if your_turn else "Tocca ad AURA"
        check = "  \u2014 Scacco!" if b.in_check() else ""
        status.setText(f"{who} ({side}){check}")

    def update_stats_label():
        st = load_stats()
        wins = st.get("wins", 0); losses = st.get("losses", 0); draws = st.get("draws", 0)
        total = wins + losses + draws
        if total == 0:
            stats_label.setText("Nessuna partita ancora. In bocca al lupo!")
        else:
            stats_label.setText(
                f"Storico vs AURA \u2014 {wins}V / {losses}S / {draws}P  (su {total})"
            )

    def set_board_enabled(enabled: bool):
        for btn in squares.values():
            btn.setEnabled(enabled)

    # ---------- Logica di gioco ----------

    def on_square_click(square: int):
        b = state["board"]
        if state["game_over"] or state["ai_thinking"] or state["animating"]:
            return
        if b.turn != state["player_color"]:
            return

        sel = state["selected"]
        # se ho gia' selezionato e clicco una destinazione legale -> muovo
        if sel is not None:
            move = next((m for m in state["legal_from_sel"] if m.to == square), None)
            if move is not None:
                _finalize_player_move(move)
                return
        # altrimenti: seleziona se e' un mio pezzo
        p = b.board[square]
        if p != EMPTY and piece_color(p) == state["player_color"]:
            state["selected"] = square
            state["legal_from_sel"] = legal_targets_from(square)
            refresh_board()
        else:
            state["selected"] = None
            state["legal_from_sel"] = []
            refresh_board()

    def _finalize_player_move(move: Move):
        # gestione promozione: se ci sono piu' mosse stessa destinazione (promo)
        promos = [m for m in state["legal_from_sel"]
                  if m.to == move.to and m.flag == "p"]
        chosen = move
        if promos:
            piece = _ask_promotion()
            chosen = next((m for m in promos if m.promo == piece), promos[0])

        # togli selezione/evidenziazioni e blocca la scacchiera durante il volo
        state["selected"] = None
        state["legal_from_sel"] = []
        set_board_enabled(False)
        refresh_board()

        def after_player():
            state["player_moves"] += 1
            if _check_game_over():
                return
            _start_ai()

        _animate_move(chosen, after_player)

    def _ask_promotion() -> str:
        items = ["Donna", "Torre", "Alfiere", "Cavallo"]
        mapping = {"Donna": "Q", "Torre": "R", "Alfiere": "B", "Cavallo": "N"}
        choice, ok = QInputDialog.getItem(
            window, "Promozione", "Promuovi il pedone a:", items, 0, False
        )
        if not ok or choice not in mapping:
            return "Q"
        return mapping[choice]

    def _start_ai():
        if state["closed"]:
            return
        state["ai_thinking"] = True
        set_board_enabled(False)
        refresh_status()
        try:
            window.set_state("thinking", "scacchi: AURA pensa")
        except Exception:
            pass
        worker = ChessAIWorker(state["board"].fen(), state["difficulty"])
        worker.move_ready.connect(_on_ai_move)
        state["ai_worker"] = worker
        worker.start()

    def _on_ai_move(uci: str):
        if state["closed"]:
            return
        state["ai_thinking"] = False
        b = state["board"]
        move = _match_legal(uci)
        if move is None:
            # fallback: scegli sul momento (non dovrebbe servire)
            move = select_ai_move(b, state["difficulty"])
        if move is None:
            set_board_enabled(True)
            refresh_status()
            return

        def after_ai():
            try:
                window.set_state("idle", "scacchi")
            except Exception:
                pass
            if not _check_game_over():
                set_board_enabled(True)

        _animate_move(move, after_ai)

    def _match_legal(uci: str) -> Move | None:
        if not uci or len(uci) < 4:
            return None
        try:
            frm = algebraic_to_sq(uci[0:2])
            to = algebraic_to_sq(uci[2:4])
            promo = uci[4].upper() if len(uci) > 4 else ""
        except Exception:
            return None
        for m in state["board"].legal_moves():
            if m.frm == frm and m.to == to and (m.promo or "") == promo:
                return m
        return None

    def _check_game_over() -> bool:
        b = state["board"]
        res = b.result()
        if res is None:
            refresh_status()
            return False

        state["game_over"] = True
        set_board_enabled(False)
        pc = state["player_color"]
        color_name = "Bianco" if pc == WHITE else "Nero"

        if res == "draw":
            msg = "Patta."
            outcome = "draw"
            mood = ("thinking", "scacchi: patta")
        elif res == pc:
            msg = "Scacco matto \u2014 hai vinto! \U0001F3C6"
            outcome = "win"
            mood = ("happy", "scacchi: hai vinto!")
        else:
            msg = "Scacco matto \u2014 AURA vince. Rivincita?"
            outcome = "loss"
            mood = ("warning", "scacchi: AURA vince")

        status.setText(msg)
        try:
            window.set_state(*mood)
        except Exception:
            pass

        if not state["recorded"]:
            record_game(outcome, state["difficulty"], color_name, state["player_moves"])
            state["recorded"] = True
            update_stats_label()
        return True

    # ---------- Azioni dei controlli ----------

    def new_game():
        _cancel_animation()
        state["board"] = Board()
        state["player_color"] = WHITE if color_combo.currentIndex() == 0 else BLACK
        state["difficulty"] = ["facile", "medio", "difficile"][diff_combo.currentIndex()]
        state["selected"] = None
        state["legal_from_sel"] = []
        state["last_move"] = None
        state["game_over"] = False
        state["player_moves"] = 0
        state["ai_thinking"] = False
        state["recorded"] = False
        state["san_history"] = []
        build_board_grid()
        render_move_log()
        refresh_status()
        try:
            window.set_state("happy", "scacchi: nuova partita")
        except Exception:
            pass
        # se il giocatore e' il Nero, muove prima AURA (Bianco)
        if state["player_color"] == BLACK:
            _start_ai()

    def undo():
        b = state["board"]
        if state["ai_thinking"] or state["animating"] or len(b._undo_stack) == 0:
            return
        # annulla la coppia (mossa IA + mossa giocatore) per restare al proprio tratto
        b.undo_move()
        state["san_history"] = state["san_history"][:-1]
        if len(b._undo_stack) > 0 and b.turn != state["player_color"]:
            b.undo_move()
            state["san_history"] = state["san_history"][:-1]
        if state["player_moves"] > 0:
            state["player_moves"] -= 1
        state["selected"] = None
        state["legal_from_sel"] = []
        state["last_move"] = None
        state["game_over"] = False
        state["recorded"] = False
        set_board_enabled(True)
        refresh_board()
        render_move_log()
        refresh_status()

    def resign():
        if state["game_over"]:
            return
        confirm = QMessageBox.question(
            window, "Abbandono", "Vuoi davvero abbandonare la partita?"
        )
        if confirm != QMessageBox.Yes:
            return
        state["game_over"] = True
        set_board_enabled(False)
        status.setText("Hai abbandonato. AURA vince.")
        if not state["recorded"]:
            color_name = "Bianco" if state["player_color"] == WHITE else "Nero"
            record_game("loss", state["difficulty"], color_name, state["player_moves"])
            state["recorded"] = True
            update_stats_label()
        try:
            window.set_state("warning", "scacchi: abbandono")
        except Exception:
            pass

    # ---------- Wiring ----------
    new_btn.clicked.connect(new_game)
    undo_btn.clicked.connect(undo)
    resign_btn.clicked.connect(resign)

    # ---------- Montaggio ----------
    card.add_layout(controls)
    card.add_content(status)
    card.add_content(material)
    card.add_content(board_frame)
    card.add_content(moves_log)
    card.add_content(stats_label)

    # ---------- Inizializzazione ----------
    build_board_grid()
    update_stats_label()
    refresh_status()
    try:
        window.set_state("thinking", "scacchi pronto")
    except Exception:
        pass
    return card
