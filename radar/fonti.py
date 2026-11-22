"""Lettori dei siti carriere.

Ogni lettore restituisce una lista di annunci (dizionari) con questi campi:
    id, titolo, luogo, url, pubblicata (AAAA-MM-GG o ""), descrizione (può essere vuota),
    extra (testo aggiuntivo utile alla classificazione, es. "Internship"),
    dettaglio (funzione opzionale che scarica la descrizione completa: restituisce un dict
               con descrizione/luogo/pubblicata, oppure None).
La descrizione completa viene scaricata solo per gli annunci nuovi e potenzialmente interessanti.
"""

import datetime as dt
import gzip
import html
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

from classifica import PAESI, classifica, luogo_ok, pulisci_html

AGENTE = "RadarCarriere/1.0 (uso personale; una scansione all'ora)"
MAX_PER_FONTE = 2000


class ErroreFonte(Exception):
    pass


# ------------------------------------------------------------------ rete
def scarica(url, dati=None, intestazioni=None, tentativi=5, timeout=30, testo=False):
    corpo = None
    head = {"User-Agent": AGENTE, "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
            "Accept-Language": "it-IT,it;q=0.9,en;q=0.8", "Accept-Encoding": "gzip"}
    if dati is not None:
        corpo = json.dumps(dati).encode()
        head["Content-Type"] = "application/json"
    head.update(intestazioni or {})
    ultimo = None
    for n in range(tentativi):
        try:
            req = urllib.request.Request(url, data=corpo, headers=head, method="POST" if corpo else "GET")
            with urllib.request.urlopen(req, timeout=timeout) as r:
                grezzo = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    grezzo = gzip.decompress(grezzo)
                txt = grezzo.decode(r.headers.get_content_charset() or "utf-8", errors="replace")
                return txt if testo else json.loads(txt)
        except urllib.error.HTTPError as e:
            ultimo = f"HTTP {e.code}"
            if e.code in (400, 401, 403, 404, 405, 406, 422):
                break
            if e.code == 429:  # il sito chiede di rallentare: una sola attesa, poi si riprova al prossimo giro
                attesa = e.headers.get("Retry-After", "")
                attesa = int(attesa) if attesa.isdigit() else 20
                if n > 0 or attesa > 60 or tentativi == 1:
                    raise ErroreFonte("il sito chiede di rallentare (HTTP 429): riprovo alla prossima scansione")
                time.sleep(attesa)
                continue
        except (urllib.error.URLError, TimeoutError, ConnectionError, json.JSONDecodeError, OSError) as e:
            ultimo = str(getattr(e, "reason", e))
        time.sleep(1.5 * (n + 1))
    raise ErroreFonte(f"{ultimo} — {url[:120]}")


def oggi():
    return dt.date.today()


def data_iso(valore):
    """Converte date in vari formati (ISO, millisecondi, 'Posted 3 Days Ago') in AAAA-MM-GG."""
    if valore in (None, ""):
        return ""
    if isinstance(valore, (int, float)):
        return dt.datetime.fromtimestamp(valore / 1000 if valore > 1e11 else valore).date().isoformat()
    v = str(valore).strip()
    m = re.match(r"(\d{4}-\d{2}-\d{2})", v)
    if m:
        return m.group(1)
    low = v.lower()
    if "today" in low or "oggi" in low:
        return oggi().isoformat()
    if "yesterday" in low or "ieri" in low:
        return (oggi() - dt.timedelta(days=1)).isoformat()
    m = re.search(r"(\d+)\+?\s*(day|giorn|week|settiman|month|mes)", low)
    if m:
        n = int(m.group(1))
        unita = m.group(2)
        giorni = n * (7 if unita.startswith(("week", "settiman")) else 30 if unita.startswith(("month", "mes")) else 1)
        return (oggi() - dt.timedelta(days=giorni)).isoformat()
    return ""


def _annuncio(id, titolo, luogo, url, pubblicata="", descrizione="", extra="", dettaglio=None):
    return {"id": id, "titolo": (titolo or "").strip(), "luogo": (luogo or "").strip(), "url": url,
            "pubblicata": pubblicata or "", "descrizione": descrizione or "", "extra": extra or "",
            "dettaglio": dettaglio}


# ------------------------------------------------------------------ Workday
def _facets_piatte(facets):
    for f in facets or []:
        valori = f.get("values") or []
        if valori and "facetParameter" in valori[0]:
            yield from _facets_piatte(valori)
        else:
            yield f


def workday(fonte, paesi):
    """Banche e grandi aziende su Workday (es. https://db.wd3.myworkdayjobs.com/DBWebsite)."""
    host, tenant, sito = fonte["host"], fonte["tenant"], fonte["sito"]
    base = f"https://{host}/wday/cxs/{tenant}/{sito}"

    def pagina(filtri, offset):
        return scarica(base + "/jobs", {"appliedFacets": filtri, "limit": 20, "offset": offset, "searchText": ""})

    primo = pagina({}, 0)
    ricerche = []
    filtra_localmente = False
    if paesi:
        facets = list(_facets_piatte(primo.get("facets")))
        f_paese = next((f for f in facets if "country" in f.get("facetParameter", "").lower()), None)
        f_luogo = next((f for f in facets if f.get("facetParameter", "").lower() in ("locations", "location")), None)
        if f_paese:
            ids = [v["id"] for v in f_paese.get("values", []) if luogo_ok(v.get("descriptor", ""), paesi)]
            if ids:
                ricerche.append({f_paese["facetParameter"]: ids})
        elif f_luogo:
            ids = [v["id"] for v in f_luogo.get("values", []) if luogo_ok(v.get("descriptor", ""), paesi)]
            if ids:
                ricerche.append({f_luogo["facetParameter"]: ids})
        else:
            ricerche.append({})
            filtra_localmente = True
    else:
        ricerche.append({})

    visti, risultati = set(), []
    for filtri in ricerche:
        offset, totale = 0, None
        while offset < MAX_PER_FONTE:
            dati = primo if (not filtri and offset == 0) else pagina(filtri, offset)
            if totale is None:
                totale = dati.get("total") or 0
            lavori = dati.get("jobPostings") or []
            if not lavori:
                break
            for j in lavori:
                percorso = j.get("externalPath", "")
                codice = (j.get("bulletFields") or [percorso])[0]
                chiave = f"wd:{tenant}:{codice}"
                if chiave in visti:
                    continue
                visti.add(chiave)
                luogo = j.get("locationsText", "")
                if filtra_localmente and not luogo_ok(luogo, paesi) and not re.match(r"\d+ Locations", luogo):
                    continue
                risultati.append(_annuncio(
                    chiave, j.get("title"), luogo, f"https://{host}/en-US/{sito}{percorso}",
                    data_iso(j.get("postedOn")), dettaglio=_dettaglio_workday(base, percorso)))
            offset += len(lavori)
            if offset >= totale:
                break
            time.sleep(0.6)
    return risultati


def _dettaglio_workday(base, percorso):
    def f():
        time.sleep(0.4)
        info = scarica(base + percorso, tentativi=2).get("jobPostingInfo", {})
        luoghi = [info.get("location", "")] + (info.get("additionalLocations") or [])
        paese = (info.get("country") or {}).get("descriptor", "")
        luogo = " · ".join(x for x in luoghi if x)
        if paese and paese.lower() not in luogo.lower():
            luogo += f" ({paese})"
        return {"descrizione": pulisci_html(info.get("jobDescription", "")), "luogo": luogo,
                "pubblicata": data_iso(info.get("startDate")), "extra": info.get("timeType", "")}
    return f


# ------------------------------------------------------------------ Greenhouse
def greenhouse(fonte, paesi):
    """Es. https://boards.greenhouse.io/point72"""
    dati = scarica(f"https://boards-api.greenhouse.io/v1/boards/{fonte['slug']}/jobs?content=true")
    out = []
    for j in dati.get("jobs", []):
        luogo = (j.get("location") or {}).get("name", "")
        uffici = " · ".join(o.get("name", "") for o in j.get("offices") or [])
        tutto = f"{luogo} {uffici}"
        if not luogo_ok(tutto, paesi):
            continue
        out.append(_annuncio(f"gh:{fonte['slug']}:{j['id']}", j.get("title"), luogo or uffici,
                             j.get("absolute_url"), data_iso(j.get("first_published") or j.get("updated_at")),
                             pulisci_html(j.get("content", "")),
                             " ".join(d.get("name", "") for d in j.get("departments") or [])))
    return out


# ------------------------------------------------------------------ Lever
def lever(fonte, paesi):
    """Es. https://jobs.lever.co/palantir"""
    dominio = "api.eu.lever.co" if fonte.get("eu") else "api.lever.co"
    dati = scarica(f"https://{dominio}/v0/postings/{fonte['slug']}?mode=json")
    if isinstance(dati, dict):
        raise ErroreFonte(dati.get("error", "risposta inattesa"))
    out = []
    for j in dati:
        cat = j.get("categories") or {}
        luoghi = cat.get("allLocations") or [cat.get("location", "")]
        luogo = " · ".join(x for x in luoghi if x)
        if not luogo_ok(luogo + " " + (j.get("country") or ""), paesi):
            continue
        liste = "\n".join(f"{l.get('text', '')}\n{pulisci_html(l.get('content', ''))}" for l in j.get("lists") or [])
        descr = "\n\n".join(x for x in [j.get("descriptionPlain", ""), liste, j.get("additionalPlain", "")] if x)
        out.append(_annuncio(f"lv:{fonte['slug']}:{j['id']}", j.get("text"), luogo, j.get("hostedUrl"),
                             data_iso(j.get("createdAt")), descr, cat.get("commitment", "")))
    return out


# ------------------------------------------------------------------ SmartRecruiters
def smartrecruiters(fonte, paesi):
    """Es. https://jobs.smartrecruiters.com/BoschGroup"""
    azienda = fonte["slug"]
    codici = [p.lower() for p in paesi] or [None]
    out = []
    for codice in codici:
        offset = 0
        while offset < MAX_PER_FONTE:
            url = f"https://api.smartrecruiters.com/v1/companies/{azienda}/postings?limit=100&offset={offset}"
            if codice:
                url += f"&country={codice}"
            dati = scarica(url)
            lavori = dati.get("content") or []
            for j in lavori:
                loc = j.get("location") or {}
                livello = (j.get("experienceLevel") or {}).get("label", "")
                tipo = (j.get("typeOfEmployment") or {}).get("label", "")
                out.append(_annuncio(
                    f"sr:{azienda}:{j['id']}", j.get("name"), loc.get("fullLocation") or loc.get("city", ""),
                    f"https://jobs.smartrecruiters.com/{azienda}/{j['id']}", data_iso(j.get("releasedDate")),
                    extra=f"{livello} {tipo}", dettaglio=_dettaglio_sr(azienda, j["id"])))
            offset += len(lavori)
            if not lavori or offset >= dati.get("totalFound", 0):
                break
    return out


def _dettaglio_sr(azienda, id_):
    def f():
        d = scarica(f"https://api.smartrecruiters.com/v1/companies/{azienda}/postings/{id_}")
        sezioni = (d.get("jobAd") or {}).get("sections") or {}
        testo = "\n\n".join(pulisci_html((sezioni.get(k) or {}).get("text", ""))
                            for k in ("jobDescription", "qualifications", "additionalInformation", "companyDescription"))
        return {"descrizione": testo}
    return f


# ------------------------------------------------------------------ Ashby
def ashby(fonte, paesi):
    """Es. https://jobs.ashbyhq.com/ramp"""
    dati = scarica(f"https://api.ashbyhq.com/posting-api/job-board/{fonte['slug']}")
    out = []
    for j in dati.get("jobs", []):
        if j.get("isListed") is False:
            continue
        luoghi = [j.get("location", "")] + [s.get("location", "") for s in j.get("secondaryLocations") or []]
        luogo = " · ".join(x for x in luoghi if x)
        if not luogo_ok(luogo, paesi):
            continue
        out.append(_annuncio(f"ab:{fonte['slug']}:{j['id']}", j.get("title"), luogo, j.get("jobUrl"),
                             data_iso(j.get("publishedAt")), j.get("descriptionPlain", ""),
                             j.get("employmentType", "")))
    return out


# ------------------------------------------------------------------ Oracle Cloud (es. JPMorgan)
def oracle(fonte, paesi):
    """Es. https://jpmc.fa.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1001"""
    host, sito = fonte["host"], fonte["sito"]
    base = f"https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions"

    def chiama(extra, offset, limite=100):
        finder = f"findReqs;siteNumber={sito},facetsList=LOCATIONS,limit={limite},offset={offset},sortBy=POSTING_DATES_DESC"
        if extra:
            finder += "," + extra
        q = urllib.parse.urlencode({"onlyData": "true", "expand": "requisitionList.secondaryLocations,locationsFacet",
                                    "finder": finder}, safe=";=,")
        items = scarica(f"{base}?{q}").get("items") or [{}]
        return items[0]

    filtri = [""]
    if paesi:
        facet = chiama("", 0, 1).get("locationsFacet") or []
        nomi = {n.lower() for c in paesi for n in PAESI.get(c, ("", []))[1]}
        filtri = [f"selectedLocationsFacet={f['Id']}" for f in facet if str(f.get("Name", "")).lower() in nomi]
        if not filtri:
            return []
    out, visti = [], set()
    for filtro in filtri:
        offset = 0
        while offset < MAX_PER_FONTE:
            dati = chiama(filtro, offset)
            lavori = dati.get("requisitionList") or []
            for j in lavori:
                if j["Id"] in visti:
                    continue
                visti.add(j["Id"])
                altri = [s.get("Name", "") for s in j.get("secondaryLocations") or []]
                luogo = " · ".join(x for x in [j.get("PrimaryLocation", "")] + altri if x)
                out.append(_annuncio(
                    f"or:{host.split('.')[0]}:{j['Id']}", j.get("Title"), luogo,
                    f"https://{host}/hcmUI/CandidateExperience/en/sites/{sito}/job/{j['Id']}",
                    data_iso(j.get("PostedDate")), extra=j.get("JobFamily") or "",
                    dettaglio=_dettaglio_oracle(host, sito, j["Id"], j.get("ShortDescriptionStr", ""))))
            offset += len(lavori)
            if not lavori or offset >= (dati.get("TotalJobsCount") or 0):
                break
    return out


def _dettaglio_oracle(host, sito, id_, breve):
    def f():
        q = urllib.parse.urlencode({"onlyData": "true", "expand": "all",
                                    "finder": f'ById;Id="{id_}",siteNumber={sito}'}, safe=';=,"')
        items = scarica(f"https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails?{q}").get("items") or [{}]
        d = items[0]
        testo = "\n\n".join(pulisci_html(d.get(k) or "") for k in
                            ("ExternalDescriptionStr", "ExternalResponsibilitiesStr", "ExternalQualificationsStr"))
        return {"descrizione": testo or breve}
    return f


# ------------------------------------------------------------------ Avature (es. Deloitte Italia)
_RX_AVATURE = re.compile(r'<a[^>]+href="([^"]*/JobDetail/[^"]+)"[^>]*>(.*?)</a>(.{0,900})', re.S | re.I)


def avature(fonte, paesi):
    """Es. https://deloittecm.avature.net/en_US/careers/SearchJobs"""
    base = fonte["url"].split("?")[0].rstrip("/")
    out, visti, offset = [], set(), 0
    while offset < MAX_PER_FONTE:
        pagina = scarica(f"{base}/?jobOffset={offset}", testo=True)
        nuovi = 0
        for link, titolo, coda in _RX_AVATURE.findall(pagina):
            link = html.unescape(link)
            m = re.search(r"/(\d+)/?$", link)
            chiave = f"av:{urllib.parse.urlparse(link).netloc.split('.')[0]}:{m.group(1) if m else link}"
            if chiave in visti:
                continue
            visti.add(chiave)
            nuovi += 1
            seniority = re.search(r'jobSeniority">([^<]+)', coda)
            out.append(_annuncio(chiave, pulisci_html(titolo), "", link,
                                 extra=seniority.group(1) if seniority else "",
                                 dettaglio=_dettaglio_avature(link)))
        if not nuovi:
            break
        offset += nuovi
        time.sleep(0.3)
    return out


def _campo_avature(testo, etichetta):
    m = re.search(rf"\n\s*{etichetta}\s*\n\s*([^\n]+)", testo)
    return m.group(1).strip() if m else ""


def _dettaglio_avature(link):
    def f():
        pagina = scarica(link, testo=True)
        i = pagina.find("article__content")
        corpo = pagina[pagina.find(">", i) + 1:] if i >= 0 else pagina
        fine = corpo.find("Apply now")
        testo = pulisci_html(corpo[:fine if fine > 0 else 20000])
        inizio = testo.find("What impact will you make?")  # salta l'intestazione già mostrata nel radar
        if inizio > 0:
            testo = testo[inizio + len("What impact will you make?"):].lstrip().removeprefix("What impact will you make?").lstrip()
        testo_righe = "\n" + re.sub(r"<[^>]+>", "\n", corpo[:6000])
        return {"descrizione": testo[:8000], "luogo": _campo_avature(testo_righe, "Location"),
                "extra": _campo_avature(testo_righe, "Seniority")}
    return f


# ------------------------------------------------------------------ Adzuna (aggregatore, chiave gratuita)
PAROLE_ADZUNA = ("intern internship stage tirocinio stagista graduate neolaureato junior trainee "
                 "praktikum werkstudent stagiaire")


def adzuna(fonte, paesi, chiavi):
    if not chiavi.get("app_id") or not chiavi.get("app_key"):
        raise ErroreFonte("manca la chiave Adzuna (gratuita): inseriscila in Impostazioni")
    supportati = {"GB", "IT", "DE", "FR", "ES", "NL", "BE", "CH", "AT", "PL", "US", "SG"}
    filtro = [a.lower() for a in fonte.get("solo_aziende", [])]
    out = []
    for codice in [p for p in (paesi or ["IT"]) if p in supportati]:
        for pagina in range(1, fonte.get("pagine", 4) + 1):
            q = urllib.parse.urlencode({"app_id": chiavi["app_id"], "app_key": chiavi["app_key"],
                                        "results_per_page": 50, "what_or": PAROLE_ADZUNA,
                                        "max_days_old": 30, "sort_by": "date"})
            dati = scarica(f"https://api.adzuna.com/v1/api/jobs/{codice.lower()}/search/{pagina}?{q}")
            risultati = dati.get("results") or []
            for j in risultati:
                azienda = (j.get("company") or {}).get("display_name", "")
                if filtro and not any(f in azienda.lower() for f in filtro):
                    continue
                a = _annuncio(f"az:{j.get('id')}", j.get("title"), (j.get("location") or {}).get("display_name", ""),
                              j.get("redirect_url"), data_iso(j.get("created")), pulisci_html(j.get("description", "")),
                              j.get("contract_type") or "")
                a["azienda"] = azienda
                out.append(a)
            if len(risultati) < 50:
                break
    return out


# ------------------------------------------------------------------ pagina generica
class _Link(HTMLParser):
    def __init__(self):
        super().__init__()
        self.link, self._href, self._testo = [], None, []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._href, self._testo = dict(attrs).get("href"), []

    def handle_data(self, data):
        if self._href is not None:
            self._testo.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._href:
            self.link.append((self._href, " ".join("".join(self._testo).split())))
            self._href = None


def pagina(fonte, paesi):
    """Qualsiasi pagina 'lavora con noi': prende i link il cui testo sembra un annuncio adatto a te."""
    testo = scarica(fonte["url"], testo=True)
    p = _Link()
    p.feed(testo)
    out, visti = [], set()
    for href, titolo in p.link:
        if not (6 <= len(titolo) <= 160) or href.startswith(("mailto:", "javascript:", "#")):
            continue
        cats, rilevanza = classifica(titolo)
        if rilevanza < 2:
            continue
        url = urllib.parse.urljoin(fonte["url"], href)
        if url in visti:
            continue
        visti.add(url)
        out.append(_annuncio(f"pg:{url}", titolo, fonte.get("luogo", ""), url))
    return out


LETTORI = {"workday": workday, "greenhouse": greenhouse, "lever": lever, "smartrecruiters": smartrecruiters,
           "ashby": ashby, "oracle": oracle, "avature": avature, "pagina": pagina}


def leggi(fonte, paesi, chiavi=None):
    if fonte["tipo"] == "adzuna":
        return adzuna(fonte, paesi, chiavi or {})
    if fonte["tipo"] not in LETTORI:
        raise ErroreFonte(f"tipo di fonte sconosciuto: {fonte['tipo']}")
    return LETTORI[fonte["tipo"]](fonte, paesi)


# ------------------------------------------------------------------ riconoscimento da URL
def da_url(url):
    """Dato l'indirizzo della pagina carriere di un'azienda, capisce quale sistema usa."""
    url = url.strip()
    if not re.match(r"https?://", url):
        url = "https://" + url
    u = urllib.parse.urlparse(url)
    host, parti = u.netloc.lower(), [p for p in u.path.split("/") if p]
    if host.endswith("myworkdayjobs.com"):
        parti = [p for p in parti if not re.fullmatch(r"[a-z]{2}-[A-Z]{2}", p)]
        if not parti:
            raise ValueError("nell'indirizzo Workday manca il nome del sito (es. .../en-US/NomeSito)")
        return {"tipo": "workday", "host": host, "tenant": host.split(".")[0], "sito": parti[0]}
    if host.endswith("myworkdaysite.com") and len(parti) >= 3 and parti[0] == "recruiting":
        return {"tipo": "workday", "host": host, "tenant": parti[1], "sito": parti[2]}
    if "greenhouse.io" in host:
        slug = parse_qs_primo(u.query, "for") or (parti[0] if parti else "")
        if parti[:1] == ["embed"]:
            slug = parse_qs_primo(u.query, "for")
        return {"tipo": "greenhouse", "slug": slug}
    if host.endswith("lever.co"):
        return {"tipo": "lever", "slug": parti[0], "eu": ".eu." in host}
    if "smartrecruiters.com" in host:
        return {"tipo": "smartrecruiters", "slug": parti[0]}
    if host == "jobs.ashbyhq.com":
        return {"tipo": "ashby", "slug": parti[0]}
    if host.endswith("oraclecloud.com") and "sites" in parti:
        return {"tipo": "oracle", "host": host, "sito": parti[parti.index("sites") + 1]}
    if host.endswith("avature.net"):
        i = parti.index("careers") if "careers" in parti else len(parti)
        return {"tipo": "avature", "url": f"https://{host}/{'/'.join(parti[:i + 1])}/SearchJobs"}
    return {"tipo": "pagina", "url": url}


def parse_qs_primo(query, nome):
    return (urllib.parse.parse_qs(query).get(nome) or [""])[0]
