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

from classifica import PAESI, classifica, luogo_ok, paesi_ampi, pulisci_html

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
_RX_AVATURE = re.compile(r'<a[^>]+href="([^"]*/(?:JobDetail|FolderDetail)/[^"]+)"[^>]*>(.*?)</a>(.{0,900})', re.S | re.I)


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


_SEMBRA_ANNUNCIO = re.compile(r"\d{3,}|/jobs?/|/job-|/offer|/offerta|/position|/posizion|/vacanc|/annunc|"
                              r"/opening|/role/|/careers/[a-z0-9-]{12,}|/stage-|/internship|/opportunit|"
                              r"/concors[io]-|/bando|/bandi/|/tirocini?-|/selezion[ei]-|/avviso")
_NAVIGAZIONE = re.compile(r"/(index\.html)?$|emanati|conclus|chius|faq|privacy|cookie|spontane|iter-di", re.I)


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
        if rilevanza < 1 and not fonte.get("categoria"):
            continue
        url = urllib.parse.urljoin(fonte["url"], href)
        percorso = urllib.parse.urlparse(url).path.lower()
        completo = percorso + "?" + urllib.parse.urlparse(url).query
        if url in visti or not _SEMBRA_ANNUNCIO.search(completo) or url.rstrip("/") == fonte["url"].rstrip("/") \
                or (fonte.get("categoria") and _NAVIGAZIONE.search(percorso)):
            continue
        visti.add(url)
        out.append(_annuncio(f"pg:{url}", titolo, fonte.get("luogo", ""), url))
    return out


# ------------------------------------------------------------------ Recruitee
def recruitee(fonte, paesi):
    """Es. https://gpbullhound.recruitee.com"""
    slug = fonte["slug"]
    out = []
    for o in scarica(f"https://{slug}.recruitee.com/api/offers/").get("offers", []):
        luogo = o.get("location") or ", ".join(x for x in (o.get("city"), o.get("country")) if x)
        if not luogo_ok(luogo, paesi):
            continue
        out.append(_annuncio(f"rc:{slug}:{o['id']}", o.get("title"), luogo,
                             o.get("careers_url") or f"https://{slug}.recruitee.com/o/{o.get('slug', '')}",
                             data_iso(o.get("published_at") or o.get("created_at")),
                             pulisci_html((o.get("description") or "") + " " + (o.get("requirements") or "")),
                             o.get("employment_type_code") or ""))
    return out


# ------------------------------------------------------------------ Personio
def personio(fonte, paesi):
    """Es. https://clearwater.jobs.personio.de"""
    import xml.etree.ElementTree as ET
    slug, dominio = fonte["slug"], fonte.get("dominio", "jobs.personio.de")
    radice = ET.fromstring(scarica(f"https://{slug}.{dominio}/xml?language=en", testo=True).encode())
    out = []
    for p in radice.iter("position"):
        testo = lambda t: (p.findtext(t) or "").strip()  # noqa: E731
        uffici = [testo("office")] + [o.text or "" for o in p.iter("office")][1:]
        luogo = " · ".join(dict.fromkeys(u for u in uffici if u))
        if not luogo_ok(luogo, paesi):
            continue
        descr = "\n\n".join(pulisci_html(v.text or "") for v in p.iter("value"))
        out.append(_annuncio(f"ps:{slug}:{testo('id')}", testo("name"), luogo,
                             f"https://{slug}.{dominio}/job/{testo('id')}", data_iso(testo("createdAt")),
                             descr, f"{testo('employmentType')} {testo('seniority')}"))
    return out


# ------------------------------------------------------------------ Pinpoint
def pinpoint(fonte, paesi):
    """Es. https://lichfields.pinpointhq.com"""
    slug = fonte["slug"]
    out = []
    for o in scarica(f"https://{slug}.pinpointhq.com/postings.json").get("data", []):
        loc = o.get("location") or {}
        luogo = loc.get("name") or ", ".join(x for x in (loc.get("city"), loc.get("country")) if x)
        if not luogo_ok(luogo, paesi):
            continue
        out.append(_annuncio(f"pp:{slug}:{o['id']}", o.get("title"), luogo, o.get("url"),
                             data_iso(o.get("posted_at") or o.get("created_at")),
                             pulisci_html(o.get("description") or ""), o.get("employment_type_text") or ""))
    return out


# ------------------------------------------------------------------ Eightfold
def eightfold(fonte, paesi):
    """Es. https://mlp.eightfold.ai/careers (Millennium)"""
    host, dominio = fonte["host"], fonte["dominio"]
    out, start = [], 0
    while start < MAX_PER_FONTE:
        d = scarica(f"https://{host}/api/apply/v2/jobs?domain={dominio}&start={start}&num=100&sort_by=timestamp")
        posizioni = d.get("positions") or []
        for o in posizioni:
            luogo = " · ".join(o.get("locations") or [o.get("location") or ""])
            if not luogo_ok(luogo, paesi):
                continue
            out.append(_annuncio(f"ef:{dominio}:{o['id']}", o.get("name"), luogo,
                                 o.get("canonicalPositionUrl") or f"https://{host}/careers?pid={o['id']}",
                                 data_iso(o.get("t_create")), pulisci_html(o.get("job_description") or ""),
                                 o.get("department") or ""))
        start += len(posizioni)
        if not posizioni or start >= (d.get("count") or 0):
            break
    return out


# ------------------------------------------------------------------ iCIMS
_RX_ICIMS = re.compile(r'href="(https://[^"]+/jobs/(\d+)/[^"]*/job)[^"]*"[^>]*>(.*?)</a>(.{0,1500})', re.S | re.I)


def icims(fonte, paesi):
    """Es. https://careers-stifel.icims.com/jobs"""
    host = fonte["host"]
    out, visti = [], set()
    for pagina_n in range(0, 40):
        html_ = scarica(f"https://{host}/jobs/search?ss=1&in_iframe=1&pr={pagina_n}", testo=True)
        nuovi = 0
        for link, id_, titolo, coda in _RX_ICIMS.findall(html_):
            if id_ in visti:
                continue
            visti.add(id_)
            nuovi += 1
            titolo = re.sub(r"^\s*(?:Job\s+)?Title\s*", "", pulisci_html(titolo), flags=re.I).strip()
            luogo = ""
            m = re.search(r"(?:Location|Locations)[^<]*</span>\s*<span[^>]*>([^<]+)", coda, re.I) or \
                re.search(r">\s*([A-Z]{2}-[^<]{2,60})<", coda)
            if m:
                luogo = pulisci_html(m.group(1))
            if luogo and not luogo_ok(luogo, paesi) and re.search(r"[A-Z]{2}-", luogo) and \
                    not luogo_ok(luogo.replace("UK-", "United Kingdom ").replace("GB-", "United Kingdom ")
                                 .replace("FR-", "France ").replace("IT-", "Italy "), paesi):
                continue
            out.append(_annuncio(f"ic:{host.split('.')[0]}:{id_}", titolo, luogo, link.split("?")[0]))
        if not nuovi:
            break
    return out


# ------------------------------------------------------------------ feed RSS (Teamtailor, SuccessFactors, ...)
def rss(fonte, paesi):
    import xml.etree.ElementTree as ET
    radice = ET.fromstring(scarica(fonte["url"], testo=True).encode())
    out = []
    for it in radice.iter("item"):
        titolo = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        descr = pulisci_html(it.findtext("description") or "")
        luogo = " ".join((e.text or "") for e in it if "location" in e.tag.lower() or "city" in e.tag.lower())
        if luogo and not luogo_ok(luogo, paesi):
            continue
        out.append(_annuncio(f"rss:{link or titolo}", titolo, luogo, link, data_iso(it.findtext("pubDate") or ""),
                             descr))
    return out


# ------------------------------------------------------------------ SuccessFactors (feed XML)
def successfactors(fonte, paesi):
    """Es. https://career012.successfactors.eu/career?company=banquepict"""
    host, azienda = fonte["host"], fonte["azienda"]
    xml_ = scarica(f"https://{host}/career?company={azienda}&career_ns=job_listing_summary&resultType=XML", testo=True)
    out = []
    # Lettura tollerante (alcuni feed contengono caratteri non validi per un parser XML rigoroso)
    for blocco in re.findall(r"<Job>(.*?)</Job>", xml_, re.S):
        campi = {}
        for tag, valore in re.findall(r"<([A-Za-z][\w\-]*)>(.*?)</\1>", blocco, re.S):
            valore = re.sub(r"^\s*<!\[CDATA\[(.*)\]\]>\s*$", r"\1", valore, flags=re.S)
            campi[tag.lower()] = html.unescape(valore).strip()
        titolo = campi.get("jobtitle", "")
        luogo = " ".join(v for k, v in campi.items() if any(x in k for x in ("location", "city", "country", "state")))
        if luogo and not luogo_ok(luogo, paesi):
            continue
        req = campi.get("job-req-id") or campi.get("jobreqid") or campi.get("req-id") or titolo
        url = next((v for k, v in campi.items() if "url" in k and v.startswith("http")),
                   f"https://{host}/career?company={azienda}&career_ns=job_listing&career_job_req_id={req}")
        out.append(_annuncio(f"sf:{azienda}:{req}", titolo, luogo, url,
                             data_iso(campi.get("posted-date") or campi.get("posteddate") or ""),
                             pulisci_html(campi.get("job-description", ""))))
    return out


# ------------------------------------------------------------------ sitemap (siti carriere con elenco degli annunci)
def sitemap(fonte, paesi):
    """Legge la sitemap di un sito carriere (es. https://careers.ey.com/sitemap.xml): un indirizzo per annuncio.
    Titolo e città si ricavano dall'indirizzo (es. /ey/job/Milano-Audit-Junior-Associate/1234/)."""
    schema = re.compile(fonte.get("schema", r"/job/"))
    xml_ = scarica(fonte["url"], testo=True)
    out = []
    for loc in re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", xml_):
        if not schema.search(loc):
            continue
        parti = [p for p in urllib.parse.urlparse(loc).path.split("/") if p]
        slug = next((p for p in reversed(parti) if not p.isdigit() and len(p) > 8), "")
        testo = html.unescape(urllib.parse.unquote(slug)).replace("-", " ")
        if not luogo_ok(testo, paesi):
            continue
        out.append(_annuncio(f"sm:{loc}", testo, testo, loc))
    return out


LETTORI = {"workday": workday, "greenhouse": greenhouse, "lever": lever, "smartrecruiters": smartrecruiters,
           "ashby": ashby, "oracle": oracle, "avature": avature, "pagina": pagina,
           "recruitee": recruitee, "personio": personio, "pinpoint": pinpoint, "eightfold": eightfold,
           "icims": icims, "rss": rss, "successfactors": successfactors, "sitemap": sitemap}


def leggi(fonte, paesi, chiavi=None):
    paesi = paesi_ampi(paesi)  # qui si scarica per paese; il filtro per città (Londra, Parigi) lo fa il motore
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
    if host.endswith("recruitee.com"):
        return {"tipo": "recruitee", "slug": host.split(".")[0]}
    if ".jobs.personio." in host:
        return {"tipo": "personio", "slug": host.split(".")[0], "dominio": host.split(".", 1)[1]}
    if host.endswith("pinpointhq.com"):
        return {"tipo": "pinpoint", "slug": host.split(".")[0]}
    if host.endswith("eightfold.ai"):
        dom = parse_qs_primo(u.query, "domain") or (host.split(".")[0] + ".com")
        return {"tipo": "eightfold", "host": host if host != "app.eightfold.ai" else host, "dominio": dom}
    if host.endswith("icims.com") and host not in ("www.icims.com", "icims.com"):
        return {"tipo": "icims", "host": host}
    if "successfactors." in host and parse_qs_primo(u.query, "company"):
        return {"tipo": "successfactors", "host": host, "azienda": parse_qs_primo(u.query, "company")}
    if u.path.endswith("sitemap.xml"):
        return {"tipo": "sitemap", "url": url}
    if u.path.endswith((".rss", "/rss")) or "/services/rss/" in u.path:
        return {"tipo": "rss", "url": url}
    if host.endswith("avature.net"):
        i = parti.index("careers") if "careers" in parti else len(parti)
        return {"tipo": "avature", "url": f"https://{host}/{'/'.join(parti[:i + 1])}/SearchJobs"}
    for segno in ("SearchJobs", "JobDetail", "FolderDetail"):  # Avature con dominio proprio (es. Bain, BCG, UniCredit)
        if segno in parti:
            return {"tipo": "avature", "url": f"https://{host}/{'/'.join(parti[:parti.index(segno)])}/SearchJobs"}
    return {"tipo": "pagina", "url": url}


def parse_qs_primo(query, nome):
    return (urllib.parse.parse_qs(query).get(nome) or [""])[0]
