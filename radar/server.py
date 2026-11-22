"""Piccolo server web locale: serve il terminale (web/index.html) e le API JSON."""

import json
import os
import re
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import fonti
from classifica import CATEGORIE, PAESI

WEB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")


def crea_server(radar, porta):
    class Gestore(BaseHTTPRequestHandler):
        def log_message(self, *a):  # silenzia il log di ogni richiesta
            pass

        # ------------------------------------------------ utilità
        def _json(self, dati, codice=200):
            corpo = json.dumps(dati, ensure_ascii=False).encode()
            self.send_response(codice)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(corpo)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(corpo)

        def _corpo(self):
            n = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(n) or b"{}") if n else {}

        def _locale(self):
            # Accetta solo richieste dal tuo PC (protezione contro altri siti aperti nel browser)
            origine = self.headers.get("Origin") or ""
            return not origine or re.match(r"https?://(127\.0\.0\.1|localhost)(:\d+)?$", origine)

        # ------------------------------------------------ GET
        def do_GET(self):
            u = urllib.parse.urlparse(self.path)
            if u.path in ("/", "/index.html"):
                with open(os.path.join(WEB, "index.html"), "rb") as f:
                    corpo = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(corpo)))
                self.end_headers()
                self.wfile.write(corpo)
            elif u.path == "/api/offerte":
                self._json(radar.archivio.offerte(1))
            elif u.path.startswith("/api/offerta/"):
                o = radar.archivio.offerta(urllib.parse.unquote(u.path[len("/api/offerta/"):]))
                self._json(o or {"errore": "non trovata"}, 200 if o else 404)
            elif u.path == "/api/stato":
                self._json(self._stato())
            elif u.path == "/api/fonti":
                stati = radar.archivio.stati_fonti()
                self._json([dict(a, stato=stati.get(a["nome"])) for a in radar.aziende()])
            elif u.path == "/api/impostazioni":
                imp = radar.impostazioni()
                self._json({"impostazioni": imp, "paesi": {k: v[0] for k, v in PAESI.items()},
                            "categorie": CATEGORIE})
            else:
                self.send_error(404)

        def _stato(self):
            prossima = radar.prossima_scansione
            return {"in_corso": radar.in_corso, "avanzamento": radar.avanzamento,
                    "ultima": radar.ultima_scansione,
                    "prossima_tra_s": max(0, int(prossima - time.time())) if prossima else None,
                    "conteggi": radar.archivio.conteggi(), "registro": radar.registro[-40:]}

        # ------------------------------------------------ POST
        def do_POST(self):
            if not self._locale():
                return self._json({"errore": "richiesta non consentita"}, 403)
            u = urllib.parse.urlparse(self.path)
            try:
                dati = self._corpo()
            except json.JSONDecodeError:
                return self._json({"errore": "JSON non valido"}, 400)

            if u.path.startswith("/api/offerta/"):
                radar.archivio.aggiorna(urllib.parse.unquote(u.path[len("/api/offerta/"):]), **dati)
                self._json({"ok": True})
            elif u.path == "/api/lette":
                radar.archivio.segna_tutte_lette()
                self._json({"ok": True})
            elif u.path == "/api/scansiona":
                self._json({"avviata": radar.scansiona_subito(dati.get("solo"))})
            elif u.path == "/api/impostazioni":
                self._json({"impostazioni": radar.salva_impostazioni(dati)})
            elif u.path == "/api/fonti/aggiungi":
                self._aggiungi(dati)
            elif u.path == "/api/fonti/modifica":
                aziende = radar.aziende()
                for a in aziende:
                    if a["nome"] == dati.get("nome"):
                        if "attiva" in dati:
                            a["attiva"] = bool(dati["attiva"])
                        if "settore" in dati:
                            a["settore"] = dati["settore"]
                if dati.get("elimina"):
                    aziende = [a for a in aziende if a["nome"] != dati.get("nome")]
                radar.salva_aziende(aziende)
                self._json({"ok": True})
            else:
                self.send_error(404)

        def _aggiungi(self, dati):
            nome = (dati.get("nome") or "").strip()
            if not nome or not dati.get("url"):
                return self._json({"errore": "servono nome e indirizzo"}, 400)
            if any(a["nome"] == nome for a in radar.aziende()):
                return self._json({"errore": "esiste già una fonte con questo nome"}, 400)
            try:
                fonte = fonti.da_url(dati["url"])
            except ValueError as e:
                return self._json({"errore": str(e)}, 400)
            fonte.update(nome=nome, settore=dati.get("settore") or "Altro", attiva=True)
            # Prova subito la fonte, così sai se funziona
            try:
                annunci = fonti.leggi(fonte, radar.impostazioni()["paesi"])
                esito = f"funziona: {len(annunci)} annunci nei paesi scelti"
            except Exception as e:
                return self._json({"errore": f"non riesco a leggere questa pagina ({e})", "fonte": fonte}, 400)
            radar.salva_aziende(radar.aziende() + [fonte])
            radar.scansiona_subito(nome)
            self._json({"ok": True, "fonte": fonte, "esito": esito})

    return ThreadingHTTPServer(("127.0.0.1", porta), Gestore)
