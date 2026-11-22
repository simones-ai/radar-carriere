"""Trova da solo dove pubblica le offerte di lavoro ogni azienda di elenco.json.

Per ogni azienda:
1. visita il sito e le pagine "careers / lavora con noi" più comuni;
2. raccoglie i collegamenti ai sistemi di selezione (Workday, Greenhouse, Lever, SmartRecruiters, ...);
3. prova anche i sistemi più diffusi con nomi ricavati da quello dell'azienda;
4. per ogni sistema trovato verifica che il radar riesca davvero a leggerlo.

Stampa una riga "RISULTATO {json}" per azienda. Uso: python radar/scoperta/scopri.py [nome-filtro]
"""

import json
import os
import re
import sys
import unicodedata
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

QUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(QUI))

import fonti  # noqa: E402

PAESI = ["IT", "GB", "FR"]
PERCORSI = ["", "/careers", "/careers/", "/en/careers", "/en/careers/", "/it/careers", "/careers/jobs",
            "/jobs", "/join-us", "/en/join-us", "/lavora-con-noi", "/it/lavora-con-noi", "/carriere",
            "/it/carriere", "/en/about-us/careers", "/work-with-us", "/en/work-with-us", "/people/careers"]
ATS = re.compile(
    r"""https?://[^"'\s<>()]*(?:myworkdayjobs\.com|myworkdaysite\.com|greenhouse\.io|lever\.co|smartrecruiters\.com|"""
    r"""ashbyhq\.com|oraclecloud\.com|avature\.net|successfactors\.(?:com|eu)|jobs2web|workable\.com|teamtailor\.com|"""
    r"""personio\.(?:de|com)|recruitee\.com|bamboohr\.com|icims\.com|taleo\.net|eightfold\.ai|inrecruiting\.com|"""
    r"""intervieweb\.it|altamiraweb|zucchetti|jobvite\.com|phenompeople|welcometothejungle\.com|breezy\.hr|"""
    r"""join\.com|softgarden|pinpointhq\.com|hibob\.com|rippling|dayforcehcm\.com|cornerstoneondemand)[^"'\s<>()]*""",
    re.I)
LINK = re.compile(r"""href=["']([^"'#]+)["'][^>]*>(.{0,200}?)</a>""", re.I | re.S)
PAROLE_CARRIERE = re.compile(r"career|carrier|lavora|join|jobs|vacanc|opportunit|recruit|talent|graduate|"
                             r"stage|intern|work with|work-with|lavorare|posizioni|candidat", re.I)


def pagina(url):
    try:
        return fonti.scarica(url, tentativi=1, timeout=15, testo=True)
    except Exception:
        return None


def slug_varianti(nome):
    base = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode().lower()
    base = re.sub(r"\(.*?\)", "", base)
    parole = re.findall(r"[a-z0-9]+", base.replace("&", " and "))
    via = [p for p in parole if p not in ("and", "co", "the", "group", "sgr", "spa", "management", "partners",
                                          "capital", "asset", "international", "investments")]
    cand = ["".join(parole), "-".join(parole), "".join(via), "-".join(via), parole[0] if parole else ""]
    return [c for c in dict.fromkeys(cand) if len(c) >= 2]


def prova(fonte):
    try:
        n = len(fonti.leggi(dict(fonte), PAESI))
        return n
    except Exception as e:
        return f"errore: {str(e)[:80]}"


def sonda_slug(nome):
    trovate = []
    for s in slug_varianti(nome):
        for fonte in ({"tipo": "greenhouse", "slug": s}, {"tipo": "lever", "slug": s},
                      {"tipo": "lever", "slug": s, "eu": True}, {"tipo": "ashby", "slug": s}):
            try:
                if fonte["tipo"] == "greenhouse":
                    d = fonti.scarica(f"https://boards-api.greenhouse.io/v1/boards/{s}/jobs", tentativi=1, timeout=15)
                    ok = isinstance(d, dict) and "jobs" in d
                elif fonte["tipo"] == "lever":
                    dom = "api.eu.lever.co" if fonte.get("eu") else "api.lever.co"
                    d = fonti.scarica(f"https://{dom}/v0/postings/{s}?mode=json&limit=1", tentativi=1, timeout=15)
                    ok = isinstance(d, list) and len(d) > 0
                else:
                    d = fonti.scarica(f"https://api.ashbyhq.com/posting-api/job-board/{s}", tentativi=1, timeout=15)
                    ok = isinstance(d, dict) and d.get("jobs") is not None
            except Exception:
                ok = False
            if ok:
                trovate.append(fonte)
        try:
            camel = "".join(w.capitalize() for w in re.findall(r"[A-Za-z0-9]+", nome))
            for sr in dict.fromkeys([camel, camel + "Group", s]):
                d = fonti.scarica(f"https://api.smartrecruiters.com/v1/companies/{sr}/postings?limit=1",
                                  tentativi=1, timeout=15)
                if d.get("totalFound"):
                    trovate.append({"tipo": "smartrecruiters", "slug": sr})
                    break
        except Exception:
            pass
    return trovate


def unisci(base, href):
    try:
        return urllib.parse.urljoin(base, href.strip())
    except ValueError:  # link malformati (es. "http://[site_url]")
        return ""


def esplora(az):
    try:
        return _esplora(az)
    except Exception as e:  # un'azienda problematica non deve fermare le altre
        return {"nome": az["nome"], "settore": az["settore"], "fonti": [], "ats_non_gestiti": [],
                "pagine_carriere": [], "errore": str(e)[:200]}


def _esplora(az):
    link_ats, pagine_carriere, visitate = set(), [], set()
    da_visitare = list(az.get("careers", []))
    for dom in az["domini"]:
        da_visitare += [f"https://{dom}{p}" for p in PERCORSI]
    secondo_giro = []
    for url in da_visitare:
        if url in visitate:
            continue
        visitate.add(url)
        html = pagina(url)
        if not html:
            continue
        if url.rstrip("/").split("/")[-1] and PAROLE_CARRIERE.search(url):
            pagine_carriere.append(url)
        link_ats.update(m.rstrip("\\.,;") for m in ATS.findall(html))
        for href, testo in LINK.findall(html):
            assoluto = unisci(url, href)
            if not assoluto:
                continue
            try:
                host = urllib.parse.urlparse(assoluto).netloc
            except ValueError:
                continue
            if ATS.match(assoluto):
                link_ats.add(assoluto)
            elif (PAROLE_CARRIERE.search(href) or PAROLE_CARRIERE.search(re.sub("<[^>]+>", "", testo))) and \
                    any(host.endswith(d.split("/")[0]) for d in az["domini"]) and len(secondo_giro) < 12:
                secondo_giro.append(assoluto)
    for url in secondo_giro:
        if url in visitate:
            continue
        visitate.add(url)
        html = pagina(url)
        if html:
            pagine_carriere.append(url)
            link_ats.update(m.rstrip("\\.,;") for m in ATS.findall(html))
            for href, _ in LINK.findall(html):
                assoluto = unisci(url, href)
                if assoluto and ATS.match(assoluto):
                    link_ats.add(assoluto)

    candidate, non_gestiti = [], set()
    for link in sorted(link_ats):
        try:
            f = fonti.da_url(link)
        except ValueError:
            non_gestiti.add(link)
            continue
        if f["tipo"] == "pagina":
            non_gestiti.add(link)
        elif f not in candidate:
            candidate.append(f)
    candidate += [f for f in sonda_slug(az["nome"]) if f not in candidate]
    candidate += [f for f in az.get("fonti", []) if f not in candidate]

    funzionanti = []
    for f in candidate[:12]:
        esito = prova(f)
        funzionanti.append({"fonte": f, "esito": esito})
    return {"nome": az["nome"], "settore": az["settore"], "fonti": funzionanti,
            "ats_non_gestiti": sorted(non_gestiti)[:8], "pagine_carriere": list(dict.fromkeys(pagine_carriere))[:6]}


def main():
    elenco = json.load(open(os.path.join(QUI, "elenco.json"), encoding="utf-8"))
    filtro = sys.argv[1].lower() if len(sys.argv) > 1 else ""
    elenco = [a for a in elenco if filtro in a["nome"].lower()]
    risultati = []
    uscita = os.path.join(QUI, "risultati.json")
    with ThreadPoolExecutor(max_workers=12) as pool:
        for r in pool.map(esplora, elenco):
            risultati.append(r)
            print("RISULTATO " + json.dumps(r, ensure_ascii=False), flush=True)
            if len(risultati) % 20 == 0:  # salvataggio parziale
                with open(uscita, "w", encoding="utf-8") as f:
                    json.dump(risultati, f, ensure_ascii=False, indent=1)
    ok = sum(1 for r in risultati if any(isinstance(f["esito"], int) for f in r["fonti"]))
    print(f"RIEPILOGO {ok}/{len(risultati)} aziende con almeno una fonte leggibile")
    with open(uscita, "w", encoding="utf-8") as f:
        json.dump(risultati, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
