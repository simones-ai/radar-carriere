"""Riconosce che tipo di posizione è un annuncio (stage, summer, graduate, junior...)
e se si trova in uno dei paesi che ti interessano."""

import html
import re

# ---------------------------------------------------------------- categorie
CATEGORIE = {
    "summer": "Summer internship",
    "offcycle": "Off-cycle",
    "stage": "Stage / Tirocinio",
    "graduate": "Graduate program",
    "junior": "Junior / Entry level",
    "insight": "Spring week / Insight",
    "possibile": "Da verificare",
}
ORDINE = ["summer", "offcycle", "graduate", "stage", "junior", "insight", "possibile"]


def _re(*parole):
    return re.compile(r"(?<![\w])(?:" + "|".join(parole) + r")(?![\w])", re.IGNORECASE)


REGOLE = {
    "summer": _re(r"summer\s+(?:intern(?:ship)?s?|analysts?|associates?|programs?|programmes?|placements?)",
                  r"summer\s+\d{4}", r"\d{4}\s+summer", r"stage\s+estivo", r"sommerpraktikum", r"summer"),
    "offcycle": _re(r"off[\s-]?cycle", r"spring\s+intern(?:ship)?s?", r"autumn\s+intern(?:ship)?s?",
                    r"winter\s+intern(?:ship)?s?", r"fall\s+intern(?:ship)?s?"),
    "insight": _re(r"spring\s+(?:week|insight)s?", r"insight\s+(?:days?|weeks?|programs?|programmes?)",
                   r"discovery\s+(?:days?|programs?|programmes?)", r"open\s+days?"),
    "stage": _re(r"intern(?:ship)?s?", r"stage", r"stages", r"stagista", r"stagiste?s?", r"stagiaire",
                 r"tirocin(?:io|i|ante|anti)", r"praktik(?:um|ant|antin)", r"werkstudent(?:in)?",
                 r"placements?", r"industrial\s+placement", r"becari[oa]", r"pr[aá]cticas", r"alternan(?:ce|t)",
                 r"working\s+student", r"co-?op", r"apprentice(?:ship)?s?"),
    "graduate": _re(r"graduates?", r"grad\s+(?:program|programme|scheme)", r"new\s+grads?",
                    r"graduate\s+(?:program|programme|scheme|trainee)s?", r"analyst\s+(?:program|programme)",
                    r"neo[-\s]?laureat[aoie]", r"laureand[aoie]", r"neolaureat[aoie]", r"early\s+careers?",
                    r"campus", r"trainee(?:ship)?s?", r"rotational", r"class\s+of\s+20\d\d",
                    r"young\s+professionals?", r"talent\s+program(?:me)?"),
    "junior": _re(r"junior", r"jr\.?", r"entry[\s-]level", r"first\s+job", r"prima\s+esperienza",
                  r"recent\s+graduates?", r"0\s*[-–]\s*[12]\s+(?:years?|anni)", r"no\s+experience",
                  r"nessuna\s+esperienza", r"berufseinsteiger(?:in)?", r"d[ée]butant"),
}

# Titoli che indicano posizioni da esperti: si scartano (a meno che non dicano anche "intern" & co.).
SENIOR = _re(r"senior", r"sr\.?", r"manager", r"director", r"vice\s+president", r"vp", r"avp", r"svp",
             r"head", r"lead", r"principal", r"partner", r"chief", r"executive\s+director", r"md",
             r"managing", r"experienced", r"esperto", r"expert", r"supervisor", r"specialista\s+senior",
             r"responsabile", r"dirigente", r"architect", r"staff\s+engineer", r"heads?\s+of")

# Titoli "neutri" che spesso sono livelli d'ingresso (Analyst nelle banche, Consultant nelle Big Four).
NEUTRI = _re(r"analyst", r"associate", r"consultant", r"consulente", r"auditor", r"revisore",
             r"assistant", r"addett[oa]", r"impiegat[oa]", r"specialist", r"engineer", r"developer",
             r"advisor", r"tax", r"audit", r"assurance", r"risk")

# Nella descrizione si cercano solo frasi inequivocabili ("stage" in inglese vuol dire anche "fase").
REGOLE_DESCR = {
    "stage": _re(r"intern(?:ship)?s?", r"tirocin(?:io|i)", r"stagista", r"stage\s+(?:curriculare|extra-?curriculare|retribuito|formativo)",
                 r"(?:uno|lo|di|in|lo\s+|per\s+uno)\s+stage", r"praktikum", r"stagiaire", r"placement\s+year"),
    "graduate": _re(r"graduate\s+(?:program|programme|scheme)s?", r"neo-?laureat[aoie]", r"laureand[aoie]",
                    r"recent(?:ly)?\s+graduat(?:es?|ed)", r"new\s+grads?", r"fresh\s+graduates?", r"early\s+careers?",
                    r"class\s+of\s+20\d\d", r"neo-?diplomat[aoie]"),
    "junior": _re(r"junior", r"entry[\s-]level", r"prima\s+esperienza", r"0\s*[-–]\s*[12]\s+(?:years?|anni)",
                  r"no\s+(?:prior\s+|previous\s+)?experience\s+(?:is\s+)?(?:required|necessary)",
                  r"nessuna\s+esperienza", r"breve\s+esperienza"),
}

ESPERIENZA = re.compile(r"(?:at\s+least|minimum(?:\s+of)?|almeno|minimo|oltre|over|more\s+than)?\s*(\d{1,2})\s*\+?\s*"
                        r"(?:[-–]\s*\d{1,2}\s*)?(?:years?|yrs|anni)", re.IGNORECASE)


def pulisci_html(testo):
    """Trasforma HTML in testo semplice."""
    if not testo:
        return ""
    testo = html.unescape(testo)
    testo = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", testo, flags=re.S | re.I)
    testo = re.sub(r"<\s*(br|/p|/li|/h\d|/div)\s*/?>", "\n", testo, flags=re.I)
    testo = re.sub(r"<li[^>]*>", "\n• ", testo, flags=re.I)
    testo = re.sub(r"<[^>]+>", " ", testo)
    testo = html.unescape(testo)
    testo = re.sub(r"[ \t\xa0]+", " ", testo)
    testo = re.sub(r"\n\s*\n+", "\n\n", testo)
    return testo.strip()


def _trova(testo):
    return {cat for cat, rx in REGOLE.items() if rx.search(testo or "")}


def anni_richiesti(descrizione):
    """Il numero di anni d'esperienza più alto chiesto nella descrizione (0 se nessuno)."""
    anni = [int(m.group(1)) for m in ESPERIENZA.finditer(descrizione or "")]
    anni = [a for a in anni if a <= 15]
    return max(anni, default=0)


def classifica(titolo, descrizione="", extra=""):
    """Restituisce (categorie, rilevanza) oppure ([], 0) se l'annuncio non ti riguarda.

    rilevanza 3 = parola chiave nel titolo (es. "Summer Analyst 2027")
    rilevanza 2 = titolo neutro/junior ma la descrizione parla di stage/neolaureati (caso Deloitte)
    rilevanza 1 = titolo neutro (Analyst, Consultant...) senza indicazioni: da verificare
    """
    titolo = titolo or ""
    nel_titolo = _trova(titolo + " " + (extra or ""))
    if "summer" in nel_titolo and not REGOLE["stage"].search(titolo) and not re.search(
            r"analyst|associate|program|placement|intern|stage", titolo, re.I):
        nel_titolo.discard("summer")  # "Summer" da solo potrebbe essere un nome proprio
    if nel_titolo & {"summer", "offcycle"}:
        nel_titolo.add("stage")

    if SENIOR.search(titolo) and not (nel_titolo - {"junior"}):
        return [], 0

    anni = anni_richiesti(descrizione)
    nella_descr = {cat for cat, rx in REGOLE_DESCR.items() if rx.search(descrizione or "")}

    if nel_titolo:
        cats, rilevanza = nel_titolo | (nella_descr & {"stage", "graduate", "junior"}), 3
    elif nella_descr and anni < 3:
        cats, rilevanza = nella_descr, 2
    elif NEUTRI.search(titolo) and anni < 3:
        cats, rilevanza = {"possibile"}, 1
    else:
        return [], 0

    if anni >= 3 and rilevanza == 3 and not (cats - {"junior"} - {"possibile"}):
        return [], 0
    return [c for c in ORDINE if c in cats], rilevanza


# ---------------------------------------------------------------- luoghi
PAESI = {
    "IT": ("Italia", ["Italy", "Italia", "Italien", "Italie", "Milan", "Milano", "Rome", "Roma", "Turin", "Torino",
                      "Bologna", "Florence", "Firenze", "Naples", "Napoli", "Padova", "Padua", "Verona", "Genova",
                      "Genoa", "Bergamo", "Brescia", "Trieste", "Bari", "Venezia", "Venice", "Modena", "Parma",
                      "Vicenza", "Treviso", "Pisa", "Catania", "Palermo", "Ancona", "Perugia", "Cagliari",
                      "Trento", "Bolzano", "Udine", "Lecce", "Pescara", "Siena", "Monza", "Varese", "Como",
                      "Lecco", "Pavia", "Cremona", "Mantova", "Piacenza", "Reggio Emilia", "Ferrara", "Ravenna",
                      "Rimini", "Forlì", "Livorno", "Lucca", "Arezzo", "Prato", "La Spezia", "Savona", "Cuneo",
                      "Alessandria", "Novara", "Asti", "Biella", "Aosta", "Pordenone", "Rovigo", "Belluno",
                      "Salerno", "Caserta", "Reggio Calabria", "Cosenza", "Messina", "Siracusa", "Sassari",
                      "Taranto", "Foggia", "Potenza", "Campobasso", "L'Aquila", "Teramo", "Latina", "Frosinone",
                      "Viterbo", "Terni", "Macerata", "Pesaro", "Ivrea", "Segrate", "Assago", "Sesto San Giovanni",
                      "Cernusco", "Vimercate", "Agrate", "Fiumicino", "Pomezia", "Remote Italy"]),
    "GB": ("Regno Unito", ["United Kingdom", "UK", "U.K.", "England", "Scotland", "Great Britain", "London",
                           "Londra", "Edinburgh", "Glasgow", "Manchester", "Birmingham", "Leeds", "Bristol",
                           "Belfast", "Cardiff", "Canary Wharf"]),
    "IE": ("Irlanda", ["Ireland", "Irlanda", "Dublin", "Dublino", "Cork"]),
    "FR": ("Francia", ["France", "Francia", "Paris", "Parigi", "Lyon", "Lione", "Marseille", "Lille", "Nice"]),
    "DE": ("Germania", ["Germany", "Germania", "Deutschland", "Frankfurt", "Francoforte", "Munich", "München",
                        "Monaco di Baviera", "Berlin", "Berlino", "Hamburg", "Düsseldorf", "Dusseldorf", "Cologne",
                        "Köln", "Stuttgart", "Eschborn"]),
    "CH": ("Svizzera", ["Switzerland", "Svizzera", "Schweiz", "Suisse", "Zurich", "Zürich", "Zurigo", "Geneva",
                        "Genève", "Ginevra", "Lugano", "Basel", "Basilea", "Lausanne", "Bern"]),
    "LU": ("Lussemburgo", ["Luxembourg", "Lussemburgo", "Luxemburg"]),
    "NL": ("Paesi Bassi", ["Netherlands", "Paesi Bassi", "Olanda", "Nederland", "Amsterdam", "Rotterdam",
                           "The Hague", "Utrecht"]),
    "BE": ("Belgio", ["Belgium", "Belgio", "Brussels", "Bruxelles", "Antwerp"]),
    "ES": ("Spagna", ["Spain", "Spagna", "España", "Madrid", "Barcelona", "Barcellona"]),
    "AE": ("Emirati Arabi", ["United Arab Emirates", "UAE", "Dubai", "Abu Dhabi"]),
    "US": ("Stati Uniti", ["United States", "USA", "U.S.", "New York", "NYC", "Boston", "Chicago",
                           "San Francisco", "Los Angeles", "Houston", "Miami", "Charlotte", "Jersey City"]),
    "GR": ("Grecia", ["Greece", "Grecia", "Athens", "Atene", "Thessaloniki", "Salonicco", "Patras", "Heraklion",
                      "Ioannina"]),
    "MT": ("Malta", ["Malta", "Mriehel", "Valletta", "Sliema", "St Julian's", "Birkirkara"]),
    "PT": ("Portogallo", ["Portugal", "Portogallo", "Lisbon", "Lisboa", "Lisbona", "Porto"]),
    "PL": ("Polonia", ["Poland", "Polonia", "Warsaw", "Warszawa", "Varsavia", "Krakow", "Kraków", "Wroclaw"]),
    "IN": ("India", ["India", "Mumbai", "Bangalore", "Bengaluru", "Pune", "Hyderabad", "Chennai", "Gurugram",
                     "Gurgaon", "Noida", "Kolkata", "New Delhi"]),
    "SG": ("Singapore", ["Singapore"]),
    "HK": ("Hong Kong", ["Hong Kong"]),
}

_CACHE = {}


def regex_luoghi(paesi):
    chiave = tuple(sorted(paesi))
    if chiave not in _CACHE:
        parole = [re.escape(p) for codice in chiave for p in PAESI.get(codice, ("", []))[1]]
        _CACHE[chiave] = re.compile(r"(?<![\w])(?:" + "|".join(parole) + r")(?![\w])", re.IGNORECASE) if parole else None
    return _CACHE[chiave]


def paese_di(luogo, paesi=None):
    """Codice ISO del primo paese (fra quelli scelti) citato nel testo del luogo, altrimenti None."""
    for codice in (paesi or PAESI):
        rx = regex_luoghi([codice])
        if rx and rx.search(luogo or ""):
            return codice
    return None


def luogo_ok(luogo, paesi):
    """True se il luogo è in uno dei paesi scelti. Se non ci sono paesi scelti, va bene tutto."""
    if not paesi:
        return True
    rx = regex_luoghi(paesi)
    return bool(rx and rx.search(luogo or ""))


def luogo_escluso(luogo, paesi):
    """True solo se il luogo è riconosciuto con certezza come fuori dai paesi scelti.
    Una città sconosciuta viene tenuta (meglio un annuncio in più che uno perso)."""
    if not paesi or not luogo or luogo_ok(luogo, paesi):
        return False
    return paese_di(luogo) is not None
