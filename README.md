# Scacchi per AURA ♟️

Gioca una partita di scacchi completa **contro AURA**, direttamente dentro
l'app. Il motore gira **in locale** (nessuna connessione di rete, nessuna
libreria esterna): solo libreria standard di Python + PySide6.

## Cosa include

- Scacchiera 8×8 cliccabile con glifi Unicode dei pezzi
- Regole complete: **arrocco** (corto e lungo), **en passant**, **promozione**,
  rilevamento di **scacco**, **scacco matto** e **stallo**
- Patta per materiale insufficiente e regola delle 50 mosse
- IA avversaria con **minimax + potatura alfa-beta** e tabelle posizionali
- Tre livelli di difficoltà: **facile**, **medio**, **difficile**
- Scelta del colore (giochi col Bianco o col Nero)
- Annulla mossa, Abbandona, Nuova partita
- Bilancio del materiale in tempo reale
- Statistiche storiche (V / S / P) salvate in `~/.aura/chess_stats.json`

L'IA viene calcolata su un **thread separato**: l'interfaccia non si blocca
mai, nemmeno al livello difficile.

## Come si gioca

1. Apri il pannello dalla chat scrivendo ad esempio `scacchi` o
   `giochiamo a scacchi`, oppure dal menu degli strumenti.
2. Scegli **difficoltà** e **colore**, poi premi **Nuova partita**.
3. **Clicca un tuo pezzo**: le caselle di destinazione legali vengono
   evidenziate (un punto per le case vuote, un bordo rosso per le catture).
4. **Clicca la destinazione** per muovere. Se promuovi un pedone, una piccola
   finestra ti chiede in quale pezzo trasformarlo.
5. AURA risponde con la sua mossa. Buona partita!

## Comandi testuali

Dalla chat puoi anche chiedere:

- `regole scacchi` / `come si gioca a scacchi` → spiegazione
- `statistiche scacchi` → il tuo bilancio contro AURA

## File del pacchetto

| File        | Ruolo                                                            |
|-------------|------------------------------------------------------------------|
| `tool.json` | Manifest dell'add-on (id, titolo, icona, parole chiave)          |
| `logic.py`  | Motore di scacchi + IA + contratto AURA (`run_chess`, `describe_chess`) |
| `panel.py`  | Interfaccia grafica della scacchiera (`build_chess_panel`)        |
| `README.md` | Questo file                                                      |

## Dettagli tecnici

- Rappresentazione interna della scacchiera in **0x88** (rilevamento fuori-bordo
  immediato, generazione mosse robusta).
- La generazione delle mosse è stata validata con **perft** contro i conteggi
  di riferimento noti (posizione iniziale, *Kiwipete*, posizioni di test per
  en passant e promozione): tutti i valori combaciano fino a profondità 3–4.
- `logic.py` non dipende da Qt e può essere importato e testato da solo.

## Note

- L'IA è pensata per essere un avversario divertente, non un motore da torneo:
  al livello "difficile" cerca a profondità 3 con ordinamento delle catture.
- Le statistiche sono locali e private: restano sul tuo computer.
