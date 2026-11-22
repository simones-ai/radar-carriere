"""Seconda verifica mirata (manutenzione): prova fonti candidate, scopre i siti Workday, stampa campioni grezzi.

Legge candidati.json: {"fonti": [{"nome": ..., ...fonte}], "workday": ["host", ...], "grezzi": ["url", ...]}
"""

import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor

QUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(QUI))

import fonti  # noqa: E402

PAESI = ["IT", "GB", "FR"]


def prova(c):
    f = {k: v for k, v in c.items() if k != "nome"}
    try:
        annunci = fonti.leggi(f, PAESI)
        esempio = [f"{a['titolo'][:60]} | {a['luogo'][:40]} | {a['url'][:90]}" for a in annunci[:6]]
        return {"nome": c["nome"], "fonte": f, "esito": len(annunci), "esempi": esempio}
    except Exception as e:
        return {"nome": c["nome"], "fonte": f, "esito": f"errore: {str(e)[:120]}"}


def siti_workday(host):
    tenant = host.split(".")[0]
    trovati = set()
    for percorso in ("/robots.txt", "/", "/en-US", "/sitemap.xml"):
        try:
            t = fonti.scarica(f"https://{host}{percorso}", tentativi=1, timeout=20, testo=True,
                              intestazioni={"Accept": "text/html,application/xhtml+xml,text/plain,*/*"})
            trovati.update(re.findall(rf"{re.escape(host)}/(?:[a-z]{{2}}-[A-Z]{{2}}/)?([A-Za-z0-9_\-]+)", t))
        except Exception:
            pass
    validi = []
    for sito in sorted(trovati - {"wday", "robots.txt", "sitemap.xml", "en-US", "job"}):
        try:
            d = fonti.scarica(f"https://{host}/wday/cxs/{tenant}/{sito}/jobs",
                              {"appliedFacets": {}, "limit": 1, "offset": 0, "searchText": ""}, tentativi=1)
            validi.append({"sito": sito, "totale": d.get("total")})
        except Exception:
            pass
    return {"host": host, "siti_visti": sorted(trovati)[:15], "validi": validi}


def grezzo(url):
    try:
        t = fonti.scarica(url, tentativi=1, timeout=20, testo=True)
        link = sorted(set(re.findall(r'href="([^"#]{12,160})"', t)))[:60]
        return {"url": url, "inizio": re.sub(r"\s+", " ", t[:3000]), "link": link}
    except Exception as e:
        return {"url": url, "errore": str(e)[:150]}


def main():
    c = json.load(open(os.path.join(QUI, "candidati.json"), encoding="utf-8"))
    out = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        out["fonti"] = list(pool.map(prova, c.get("fonti", [])))
        out["workday"] = list(pool.map(siti_workday, c.get("workday", [])))
        out["grezzi"] = list(pool.map(grezzo, c.get("grezzi", [])))
    with open(os.path.join(QUI, "risultati.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("fatto:", {k: len(v) for k, v in out.items()})


if __name__ == "__main__":
    main()
