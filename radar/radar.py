"""Radar Carriere — tiene d'occhio stage, summer/off-cycle internship, graduate program e posizioni junior.

Uso:
    python radar.py                 avvia il terminale nel browser e controlla le aziende ogni ora
    python radar.py scansiona       fa un solo giro di controllo e stampa le novità (usato anche nel cloud)
    python radar.py prova URL       verifica se riesce a leggere la pagina carriere di un'azienda
    python radar.py sito [CARTELLA]  scansiona e genera il sito statico (quello pubblicato su GitHub Pages)
"""

import os
import sys
import threading
import webbrowser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fonti  # noqa: E402
from motore import Radar  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main(argv):
    radar = Radar()
    comando = argv[0] if argv else "avvia"

    if comando == "scansiona":
        nuove = radar.scansiona() or []
        for o in nuove:
            print(f"  NUOVA  {o['azienda']} — {o['titolo']}  [{', '.join(o['categorie'])}]  {o['luogo']}\n         {o['url']}")
        return

    if comando == "sito":
        cartella = argv[1] if len(argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "sito")
        if "--senza-scansione" not in argv:
            radar.scansiona()
        crea_sito(radar, cartella)
        print(f"Sito creato in {cartella}")
        return

    if comando == "prova":
        if len(argv) < 2:
            print("Scrivi anche l'indirizzo, es.: python radar.py prova https://jobs.lever.co/azienda")
            return
        fonte = fonti.da_url(argv[1])
        print("Sistema riconosciuto:", fonte)
        annunci = fonti.leggi(fonte, radar.impostazioni()["paesi"])
        print(f"{len(annunci)} annunci nei paesi scelti. Primi 10:")
        for a in annunci[:10]:
            print(f"  - {a['titolo']}  ({a['luogo']})")
        return

    from server import crea_server
    porta = int(radar.impostazioni().get("porta", 8777))
    server = crea_server(radar, porta)
    indirizzo = f"http://127.0.0.1:{porta}"
    print("=" * 60)
    print(f"  RADAR CARRIERE attivo su {indirizzo}")
    print("  Lascia aperta questa finestra: controlla le aziende in automatico.")
    print("  Per chiudere premi Ctrl+C.")
    print("=" * 60)
    radar.avvia_ciclo()
    if "--no-browser" not in argv:
        threading.Timer(1.0, lambda: webbrowser.open(indirizzo)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nArrivederci!")


def crea_sito(radar, cartella):
    """Genera il sito statico (per GitHub Pages): pagina, dati delle posizioni, descrizioni, stato delle fonti."""
    import datetime as dt
    import json

    from classifica import CATEGORIE, PAESI

    os.makedirs(cartella, exist_ok=True)
    qui = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(qui, "web", "index.html"), encoding="utf-8") as f:
        pagina = f.read().replace("<head>", "<head>\n<script>window.RADAR_STATICO = true;</script>", 1)

    offerte = radar.archivio.esporta()
    descrizioni = {o["id"]: o.pop("descrizione") or "" for o in offerte}
    stati = radar.archivio.stati_fonti()
    imp = radar.impostazioni()
    stato = {
        "aggiornato": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "paesi": {c: PAESI[c][0] for c in imp["paesi"] if c in PAESI},
        "categorie": CATEGORIE,
        "fonti": [dict({k: v for k, v in a.items() if k in ("nome", "settore", "tipo", "url", "attiva")},
                       stato=stati.get(a["nome"])) for a in radar.aziende()],
        "registro": radar.registro[-200:],
    }
    file = {"index.html": pagina, "dati.json": offerte, "descrizioni.json": descrizioni, "stato.json": stato}
    for nome, contenuto in file.items():
        with open(os.path.join(cartella, nome), "w", encoding="utf-8") as f:
            if isinstance(contenuto, str):
                f.write(contenuto)
            else:
                json.dump(contenuto, f, ensure_ascii=False, separators=(",", ":"))
    with open(os.path.join(cartella, ".nojekyll"), "w") as f:
        f.write("")


if __name__ == "__main__":
    main(sys.argv[1:])
