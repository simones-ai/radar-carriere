"""Archivio SQLite degli annunci visti."""

import datetime as dt
import json
import sqlite3
import threading

SCHEMA = """
CREATE TABLE IF NOT EXISTS offerte (
    id TEXT PRIMARY KEY,
    azienda TEXT, settore TEXT, fonte TEXT,
    titolo TEXT, luogo TEXT, paese TEXT, url TEXT,
    pubblicata TEXT, prima_vista TEXT, ultima_vista TEXT,
    attiva INTEGER DEFAULT 1,
    categorie TEXT DEFAULT '[]', rilevanza INTEGER DEFAULT 0,
    descrizione TEXT DEFAULT '',
    nuova INTEGER DEFAULT 0, letta INTEGER DEFAULT 0,
    stato TEXT DEFAULT '', note TEXT DEFAULT '', notificata INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_ril ON offerte(rilevanza);
CREATE TABLE IF NOT EXISTS fonti_stato (
    azienda TEXT PRIMARY KEY, ok INTEGER, messaggio TEXT, controllo TEXT,
    annunci INTEGER, rilevanti INTEGER, durata REAL, scansioni INTEGER DEFAULT 0
);
"""

CAMPI_LISTA = ("id, azienda, settore, fonte, titolo, luogo, paese, url, pubblicata, prima_vista, ultima_vista, "
               "attiva, categorie, rilevanza, nuova, letta, stato, note")


def adesso():
    return dt.datetime.now().isoformat(timespec="seconds")


class Archivio:
    def __init__(self, percorso):
        self.db = sqlite3.connect(percorso, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        with self.lock:
            self.db.executescript(SCHEMA)
            colonne = {r[1] for r in self.db.execute("PRAGMA table_info(offerte)")}
            if "notificata" not in colonne:  # archivi creati prima delle email
                self.db.execute("ALTER TABLE offerte ADD COLUMN notificata INTEGER DEFAULT 0")
                self.db.commit()

    def esistenti(self, prefisso_ids):
        """Gli id già presenti in archivio fra quelli indicati."""
        ids = list(prefisso_ids)
        trovati = set()
        with self.lock:
            for i in range(0, len(ids), 500):
                blocco = ids[i:i + 500]
                q = f"SELECT id FROM offerte WHERE id IN ({','.join('?' * len(blocco))})"
                trovati.update(r[0] for r in self.db.execute(q, blocco))
        return trovati

    def segna_viste(self, ids, fonte):
        """Aggiorna 'ultima_vista' degli annunci ancora online e disattiva quelli spariti."""
        ora = adesso()
        with self.lock, self.db:
            self.db.execute("CREATE TEMP TABLE IF NOT EXISTS _visti(id TEXT PRIMARY KEY)")
            self.db.execute("DELETE FROM _visti")
            self.db.executemany("INSERT OR IGNORE INTO _visti VALUES (?)", [(i,) for i in ids])
            self.db.execute("UPDATE offerte SET ultima_vista=?, attiva=1 WHERE id IN (SELECT id FROM _visti)", (ora,))
            self.db.execute("UPDATE offerte SET attiva=0 WHERE fonte=? AND attiva=1 AND id NOT IN (SELECT id FROM _visti)",
                            (fonte,))

    def inserisci(self, o):
        ora = adesso()
        with self.lock, self.db:
            self.db.execute(
                "INSERT OR IGNORE INTO offerte (id, azienda, settore, fonte, titolo, luogo, paese, url, pubblicata, "
                "prima_vista, ultima_vista, categorie, rilevanza, descrizione, nuova) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (o["id"], o["azienda"], o.get("settore", ""), o.get("fonte", ""), o["titolo"], o["luogo"],
                 o.get("paese") or "", o["url"], o.get("pubblicata", ""), ora, ora, json.dumps(o["categorie"]),
                 o["rilevanza"], o.get("descrizione", "")[:20000], 1 if o.get("nuova") else 0))

    def offerte(self, rilevanza_min=1):
        with self.lock:
            righe = self.db.execute(f"SELECT {CAMPI_LISTA} FROM offerte WHERE rilevanza >= ? "
                                    "ORDER BY COALESCE(NULLIF(pubblicata,''), substr(prima_vista,1,10)) DESC, prima_vista DESC",
                                    (rilevanza_min,)).fetchall()
        out = []
        for r in righe:
            d = dict(r)
            d["categorie"] = json.loads(d["categorie"] or "[]")
            out.append(d)
        return out

    def esporta(self, giorni_chiuse=60):
        """Tutte le offerte rilevanti per il sito: aperte e chiuse da poco, con descrizione."""
        limite = (dt.datetime.now() - dt.timedelta(days=giorni_chiuse)).isoformat(timespec="seconds")
        with self.lock:
            righe = self.db.execute(
                f"SELECT {CAMPI_LISTA}, descrizione FROM offerte WHERE rilevanza >= 1 AND (attiva=1 OR ultima_vista >= ?) "
                "ORDER BY COALESCE(NULLIF(pubblicata,''), substr(prima_vista,1,10)) DESC, prima_vista DESC",
                (limite,)).fetchall()
        out = []
        for r in righe:
            d = dict(r)
            d["categorie"] = json.loads(d["categorie"] or "[]")
            for k in ("nuova", "letta", "stato", "note"):  # dati personali: sul sito restano nel tuo browser
                d.pop(k, None)
            out.append(d)
        return out

    def offerta(self, id_):
        with self.lock:
            r = self.db.execute("SELECT * FROM offerte WHERE id=?", (id_,)).fetchone()
        if not r:
            return None
        d = dict(r)
        d["categorie"] = json.loads(d["categorie"] or "[]")
        return d

    def aggiorna(self, id_, **campi):
        ammessi = {k: v for k, v in campi.items() if k in ("stato", "note", "letta", "nuova")}
        if not ammessi:
            return
        with self.lock, self.db:
            self.db.execute(f"UPDATE offerte SET {', '.join(f'{k}=?' for k in ammessi)} WHERE id=?",
                            (*ammessi.values(), id_))

    def segna_tutte_lette(self):
        with self.lock, self.db:
            self.db.execute("UPDATE offerte SET letta=1, nuova=0 WHERE letta=0 OR nuova=1")

    def da_notificare(self, rilevanza_min):
        """Posizioni nuove (non della prima scansione di una fonte) non ancora segnalate via email."""
        with self.lock:
            righe = self.db.execute(
                "SELECT id, azienda, settore, titolo, luogo, url, pubblicata, categorie, rilevanza FROM offerte "
                "WHERE nuova=1 AND notificata=0 AND attiva=1 AND rilevanza>=? ORDER BY rilevanza DESC, prima_vista",
                (rilevanza_min,)).fetchall()
        out = []
        for r in righe:
            d = dict(r)
            d["categorie"] = json.loads(d["categorie"] or "[]")
            out.append(d)
        return out

    def segna_notificate(self, ids):
        with self.lock, self.db:
            self.db.executemany("UPDATE offerte SET notificata=1 WHERE id=?", [(i,) for i in ids])

    def stato_fonte(self, azienda, ok, messaggio, annunci=0, rilevanti=0, durata=0.0):
        with self.lock, self.db:
            self.db.execute(
                "INSERT INTO fonti_stato (azienda, ok, messaggio, controllo, annunci, rilevanti, durata, scansioni) "
                "VALUES (?,?,?,?,?,?,?,1) ON CONFLICT(azienda) DO UPDATE SET ok=excluded.ok, messaggio=excluded.messaggio, "
                "controllo=excluded.controllo, annunci=excluded.annunci, rilevanti=excluded.rilevanti, "
                "durata=excluded.durata, scansioni=fonti_stato.scansioni+1",
                (azienda, int(ok), messaggio, adesso(), annunci, rilevanti, durata))

    def stati_fonti(self):
        with self.lock:
            return {r["azienda"]: dict(r) for r in self.db.execute("SELECT * FROM fonti_stato")}

    def gia_scansionata(self, azienda):
        with self.lock:
            r = self.db.execute("SELECT scansioni FROM fonti_stato WHERE azienda=? AND ok=1", (azienda,)).fetchone()
        return bool(r and r[0])

    def conteggi(self):
        with self.lock:
            r = self.db.execute("SELECT COUNT(*) tot, SUM(nuova=1 AND letta=0) nuove, SUM(stato='candidato') candidature, "
                                "SUM(stato='salvata') salvate FROM offerte WHERE rilevanza>=2 AND attiva=1").fetchone()
        return {k: (r[k] or 0) for k in r.keys()}
