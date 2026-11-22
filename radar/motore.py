"""Il motore: legge le fonti, classifica gli annunci, li salva e ti avvisa via email delle novità."""

import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import fonti
import notifiche
from archivio import Archivio, adesso
from classifica import PAESI, SENIOR, classifica, luogo_escluso, paese_di

CARTELLA = os.path.dirname(os.path.abspath(__file__))

IMPOSTAZIONI_BASE = {
    "paesi": ["IT", "GB"],
    "intervallo_minuti": 60,
    "adzuna": {"app_id": "", "app_key": ""},
    "porta": 8777,
    # Email per le nuove posizioni (nel cloud arrivano dai secrets EMAIL_UTENTE / EMAIL_PASSWORD / EMAIL_DESTINATARIO)
    "email": {"smtp": "smtp.gmail.com", "porta": 465, "utente": "", "password": "", "destinatario": ""},
    "email_rilevanza_min": 2,     # 2 = anche i "Junior" aperti a stagisti; 3 = solo parola chiave nel titolo
    "email_protette": False,      # True = includi le posizioni riservate alle categorie protette (L. 68/99)
}


# Nel cloud (GitHub Actions) le impostazioni arrivano dalle variabili d'ambiente / "secrets".
VARIABILI = {"ADZUNA_APP_ID": ("adzuna", "app_id"), "ADZUNA_APP_KEY": ("adzuna", "app_key"),
             "EMAIL_UTENTE": ("email", "utente"), "EMAIL_PASSWORD": ("email", "password"),
             "EMAIL_DESTINATARIO": ("email", "destinatario"), "EMAIL_SMTP": ("email", "smtp")}


def _da_ambiente(imp):
    for nome, (gruppo, chiave) in VARIABILI.items():
        if os.environ.get(nome):
            imp[gruppo][chiave] = os.environ[nome].strip()
    if os.environ.get("RADAR_PAESI"):
        imp["paesi"] = [p.strip().upper() for p in os.environ["RADAR_PAESI"].split(",") if p.strip()]
    if os.environ.get("RADAR_ATTIVA"):  # es. "Adzuna": fonti da accendere nel cloud
        imp["attiva_extra"] = [n.strip().lower() for n in os.environ["RADAR_ATTIVA"].split(",") if n.strip()]
    return imp


def _leggi_json(percorso, predefinito):
    try:
        with open(percorso, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return predefinito


def _scrivi_json(percorso, dati):
    tmp = percorso + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(dati, f, ensure_ascii=False, indent=2)
    os.replace(tmp, percorso)


class Radar:
    def __init__(self, cartella=CARTELLA):
        self.f_aziende = os.path.join(cartella, "aziende.json")
        self.f_impostazioni = os.path.join(cartella, "impostazioni.json")
        self.archivio = Archivio(os.path.join(cartella, "radar.db"))
        self.lock = threading.Lock()
        self.in_corso = False
        self.avanzamento = {"fatte": 0, "totale": 0, "corrente": ""}
        self.ultima_scansione = None
        self.prossima_scansione = None
        self.registro = []  # ultime righe di log mostrate nel terminale

    # ---------------------------------------------------------- configurazione
    def impostazioni(self):
        imp = json.loads(json.dumps(IMPOSTAZIONI_BASE))
        salvate = _leggi_json(self.f_impostazioni, {})
        for k, v in salvate.items():
            if isinstance(v, dict) and isinstance(imp.get(k), dict):
                imp[k].update(v)
            else:
                imp[k] = v
        return _da_ambiente(imp)

    def salva_impostazioni(self, nuove):
        imp = self.impostazioni()
        for k, v in nuove.items():
            if k not in IMPOSTAZIONI_BASE:
                continue
            if isinstance(v, dict) and isinstance(imp.get(k), dict):
                imp[k].update(v)
            else:
                imp[k] = v
        imp["paesi"] = [p for p in imp["paesi"] if p in PAESI]
        imp["intervallo_minuti"] = max(15, int(imp["intervallo_minuti"]))
        _scrivi_json(self.f_impostazioni, imp)
        return imp

    def aziende(self):
        return _leggi_json(self.f_aziende, [])

    def salva_aziende(self, aziende):
        _scrivi_json(self.f_aziende, aziende)

    def log(self, testo):
        riga = f"{adesso()[11:19]}  {testo}"
        print(riga, flush=True)
        self.registro = (self.registro + [riga])[-200:]

    # ---------------------------------------------------------- scansione
    def scansiona(self, solo=None):
        """Controlla tutte le fonti attive (o solo quella indicata). Restituisce le nuove offerte rilevanti."""
        with self.lock:
            if self.in_corso:
                return None
            self.in_corso = True
        try:
            imp = self.impostazioni()
            extra = imp.get("attiva_extra", [])
            elenco = [a for a in self.aziende()
                      if (a.get("attiva", True) or any(e in a["nome"].lower() for e in extra))
                      and (solo is None or a["nome"] == solo)]
            self.avanzamento = {"fatte": 0, "totale": len(elenco), "corrente": ""}
            self.log(f"Scansione di {len(elenco)} fonti — paesi: {', '.join(imp['paesi']) or 'tutti'}")
            nuove = []
            with ThreadPoolExecutor(max_workers=4) as pool:
                lavori = {pool.submit(self._scansiona_fonte, a, imp): a for a in elenco}
                for fut in as_completed(lavori):
                    a = lavori[fut]
                    self.avanzamento["fatte"] += 1
                    self.avanzamento["corrente"] = a["nome"]
                    try:
                        nuove.extend(fut.result())
                    except Exception as e:  # una fonte rotta non deve fermare le altre
                        self.archivio.stato_fonte(a["nome"], False, str(e)[:300])
                        self.log(f"  ✗ {a['nome']}: {e}")
            self.ultima_scansione = adesso()
            self.log(f"Fine scansione: {len(nuove)} nuove posizioni rilevanti")
            self._avvisa(imp)
            return nuove
        finally:
            self.in_corso = False

    def _scansiona_fonte(self, fonte, imp):
        inizio = time.time()
        if "tipo" not in fonte:  # in aziende.json basta "nome" e "url": il sistema si riconosce da solo
            fonte = dict(fonte, **fonti.da_url(fonte["url"]))
        paesi = imp["paesi"]
        prima_volta = not self.archivio.gia_scansionata(fonte["nome"])
        annunci = fonti.leggi(fonte, paesi, imp.get("adzuna"))
        ids = [a["id"] for a in annunci]
        noti = self.archivio.esistenti(ids)
        da_valutare = [a for a in annunci if a["id"] not in noti]

        # Prima passata sul solo titolo: i ruoli senior non richiedono di scaricare la descrizione.
        candidati, scartati = [], []
        for a in da_valutare:
            cats, ril = classifica(a["titolo"], "", a["extra"])
            if ril == 0 and SENIOR.search(a["titolo"] or ""):
                scartati.append(a)
            else:
                candidati.append(a)

        con_dettaglio = [a for a in candidati if a.get("dettaglio") and not a["descrizione"]]
        rinviati = set()
        if con_dettaglio:
            stop = threading.Event()  # al primo "rallenta" (HTTP 429) si smette e si riprova al prossimo giro

            def dettaglio(a):
                if stop.is_set():
                    return RINVIA
                try:
                    return a["dettaglio"]()
                except fonti.ErroreFonte as e:
                    if "429" in str(e):
                        stop.set()
                        return RINVIA
                    return None
                except Exception:
                    return None

            with ThreadPoolExecutor(max_workers=2 if fonte["tipo"] == "workday" else 4) as pool:
                for a, det in zip(con_dettaglio, pool.map(dettaglio, con_dettaglio)):
                    if det is RINVIA:
                        rinviati.add(a["id"])
                        continue
                    if det:
                        for k, v in det.items():
                            if v and (k != "extra"):
                                a[k] = v
                        if det.get("extra"):
                            a["extra"] = f"{a['extra']} {det['extra']}"

        if rinviati:
            self.log(f"  … {fonte['nome']}: il sito chiede di rallentare, "
                     f"{len(rinviati)} descrizioni rimandate al prossimo giro")
        nuove = []
        for a in candidati + scartati:
            if a["id"] in rinviati:
                continue
            luogo = a["luogo"]
            if fonte.get("paese") and not paese_di(luogo):
                luogo = f"{luogo} ({PAESI[fonte['paese']][0]})".strip()
                a["luogo"] = luogo
            cats, ril = classifica(a["titolo"], a["descrizione"], a["extra"])
            if ril and luogo_escluso(luogo, paesi):
                ril, cats = 0, []
            o = dict(a, azienda=a.get("azienda") or fonte["nome"], settore=fonte.get("settore", ""),
                     fonte=fonte["nome"], categorie=cats, rilevanza=ril, paese=paese_di(luogo, paesi),
                     nuova=not prima_volta)
            if not ril:
                o["descrizione"] = ""  # non serve conservare il testo degli annunci scartati
            self.archivio.inserisci(o)
            if ril:
                nuove.append(o)
        self.archivio.segna_viste(ids, fonte["nome"])
        self.archivio.stato_fonte(fonte["nome"], True,
                                  f"{len(annunci)} annunci nei paesi scelti, {len(da_valutare)} nuovi da valutare",
                                  len(annunci), self._rilevanti_fonte(fonte["nome"]), time.time() - inizio)
        self.log(f"  ✓ {fonte['nome']}: {len(annunci)} annunci, {len(nuove)} nuovi rilevanti"
                 + (" (prima scansione)" if prima_volta else ""))
        return nuove if not prima_volta else []

    def _rilevanti_fonte(self, nome):
        with self.archivio.lock:
            r = self.archivio.db.execute("SELECT COUNT(*) FROM offerte WHERE fonte=? AND rilevanza>=1 AND attiva=1",
                                         (nome,)).fetchone()
        return r[0]

    def _avvisa(self, imp):
        """Manda un'email con le posizioni nuove non ancora segnalate (se l'email è configurata)."""
        em = imp.get("email") or {}
        if not (em.get("utente") and em.get("password")):
            return
        offerte = [o for o in self.archivio.da_notificare(imp.get("email_rilevanza_min", 2))
                   if imp.get("email_protette") or not notifiche.PROTETTE.search(o["titolo"])]
        if not offerte:
            return
        try:
            notifiche.invia_email(em, offerte)
            self.archivio.segna_notificate([o["id"] for o in offerte])
            self.log(f"  ✉ Email inviata: {len(offerte)} nuove posizioni")
        except Exception as e:  # riprova al giro successivo
            self.log(f"  ✗ Email non inviata ({e}): riprovo al prossimo giro")

    # ---------------------------------------------------------- ciclo automatico
    def avvia_ciclo(self):
        def ciclo():
            while True:
                try:
                    self.scansiona()
                except Exception as e:
                    self.log(f"Errore nella scansione: {e}")
                minuti = self.impostazioni()["intervallo_minuti"]
                self.prossima_scansione = time.time() + minuti * 60
                while time.time() < self.prossima_scansione:
                    time.sleep(5)
        threading.Thread(target=ciclo, daemon=True).start()

    def scansiona_subito(self, solo=None):
        if self.in_corso:
            return False
        threading.Thread(target=self.scansiona, kwargs={"solo": solo}, daemon=True).start()
        return True


RINVIA = object()
