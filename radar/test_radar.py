"""Test del Radar Carriere (non usano internet). Lancia con: python -m pytest radar"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fonti  # noqa: E402
from classifica import classifica, luogo_escluso, luogo_ok, paese_di  # noqa: E402
from motore import Radar  # noqa: E402


def test_parole_chiave_nel_titolo():
    assert classifica("Summer Analyst 2027 - Investment Banking") == (["summer", "stage"], 3)
    assert classifica("Off-Cycle Internship - Equity Research")[0][0] == "offcycle"
    assert classifica("Graduate Programme 2027")[0] == ["graduate"]
    assert classifica("Stage Public Affairs Milano")[0] == ["stage"]
    assert "stage" in classifica("Tirocinio curriculare area Finance")[0]
    assert classifica("Spring Week 2027")[0][0] == "insight"


def test_junior_con_stage_nella_descrizione_caso_deloitte():
    cats, ril = classifica("Junior Consultant - Audit & Assurance",
                           "La posizione è aperta a neolaureati, con inserimento in stage o assunzione diretta.")
    assert ril == 3 and {"junior", "stage", "graduate"} <= set(cats)
    cats, ril = classifica("Consultant - Risk Advisory", "Cerchiamo laureandi o neolaureati in economia")
    assert ril == 2 and cats == ["graduate"]


def test_scarta_ruoli_senior():
    assert classifica("Senior Manager Tax")[1] == 0
    assert classifica("Vice President, Equity Sales")[1] == 0
    assert classifica("Business Analyst", "Requires 5+ years of experience")[1] == 0
    assert classifica("Head of Graduate Recruitment")[1] == 3  # parola chiave nel titolo: lo mostra comunque


def test_stage_inglese_nella_descrizione_non_conta():
    assert classifica("Consultant", "At this stage of the project you will ...") == (["possibile"], 1)


def test_summer_da_solo_non_basta():
    assert classifica("Summer Festival Coordinator")[1] == 0


def test_luoghi():
    assert luogo_ok("Milano, Via Tortona", ["IT"])
    assert not luogo_ok("Romania, Bucharest", ["IT"])  # "Roma" non deve corrispondere a "Romania"
    assert paese_di("LONDON, United Kingdom") == "GB"
    assert luogo_escluso("Athens", ["IT", "GB"])
    assert not luogo_escluso("Cittadella", ["IT"])  # città sconosciuta: si tiene
    assert not luogo_escluso("", ["IT"])


def test_riconosce_sistema_da_url():
    assert fonti.da_url("https://db.wd3.myworkdayjobs.com/en-US/DBWebsite") == \
        {"tipo": "workday", "host": "db.wd3.myworkdayjobs.com", "tenant": "db", "sito": "DBWebsite"}
    assert fonti.da_url("https://wd3.myworkdaysite.com/recruiting/acme/External")["tenant"] == "acme"
    assert fonti.da_url("https://boards.greenhouse.io/point72")["slug"] == "point72"
    assert fonti.da_url("https://job-boards.eu.greenhouse.io/imc/jobs/123")["slug"] == "imc"
    assert fonti.da_url("jobs.lever.co/palantir") == {"tipo": "lever", "slug": "palantir", "eu": False}
    assert fonti.da_url("https://jobs.smartrecruiters.com/BoschGroup")["tipo"] == "smartrecruiters"
    assert fonti.da_url("https://jpmc.fa.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1001/jobs")["sito"] == "CX_1001"
    assert fonti.da_url("https://deloittecm.avature.net/en_US/careers/SearchJobs/?jobOffset=6")["url"] == \
        "https://deloittecm.avature.net/en_US/careers/SearchJobs"
    assert fonti.da_url("https://www.esempio.it/lavora-con-noi")["tipo"] == "pagina"


def test_date():
    assert fonti.data_iso("2026-11-17T15:31:08.052Z") == "2026-11-17"
    assert fonti.data_iso("Posted Today") == fonti.oggi().isoformat()
    assert fonti.data_iso("Posted 30+ Days Ago") != ""
    assert fonti.data_iso(1700000000000).startswith("2023-")


def test_motore_nuove_posizioni_e_annunci_chiusi(tmp_path, monkeypatch):
    with open(tmp_path / "aziende.json", "w") as f:
        json.dump([{"nome": "Banca Test", "settore": "Banca", "tipo": "finta", "attiva": True}], f)
    elenco = [
        fonti._annuncio("t:1", "Summer Analyst 2027", "Milano", "https://x/1"),
        fonti._annuncio("t:2", "Managing Director", "Milano", "https://x/2"),
        fonti._annuncio("t:3", "Graduate Program", "Athens", "https://x/3"),
    ]
    monkeypatch.setattr(fonti, "leggi", lambda fonte, paesi, chiavi=None: list(elenco))
    r = Radar(str(tmp_path))
    assert r.scansiona() == []  # prima scansione: si archivia tutto senza segnalarlo come "nuovo"
    assert [o["id"] for o in r.archivio.offerte(1)] == ["t:1"]

    elenco[:] = [elenco[0], fonti._annuncio("t:4", "Off-cycle Intern - M&A", "London", "https://x/4")]
    nuove = r.scansiona()
    assert [o["id"] for o in nuove] == ["t:4"]
    assert r.archivio.offerta("t:4")["nuova"] == 1
    assert r.archivio.offerta("t:3")["attiva"] == 0  # sparito dal sito → chiuso


def test_descrizioni_rimandate_se_il_sito_chiede_di_rallentare(tmp_path, monkeypatch):
    with open(tmp_path / "aziende.json", "w") as f:
        json.dump([{"nome": "Banca Lenta", "tipo": "finta", "attiva": True}], f)

    def troppo_veloce():
        raise fonti.ErroreFonte("il sito chiede di rallentare (HTTP 429)")

    annuncio = fonti._annuncio("t:9", "Business Analyst", "Milano", "https://x/9", dettaglio=troppo_veloce)
    monkeypatch.setattr(fonti, "leggi", lambda fonte, paesi, chiavi=None: [dict(annuncio)])
    r = Radar(str(tmp_path))
    r.scansiona()
    assert r.archivio.offerta("t:9") is None  # non archiviato: verrà valutato di nuovo al prossimo giro


def test_impostazioni_dalle_variabili_ambiente(tmp_path, monkeypatch):
    monkeypatch.setenv("ADZUNA_APP_ID", " abc ")
    monkeypatch.setenv("RADAR_PAESI", "it, ie")
    imp = Radar(str(tmp_path)).impostazioni()
    assert imp["adzuna"]["app_id"] == "abc"
    assert imp["paesi"] == ["IT", "IE"]


def test_crea_sito(tmp_path, monkeypatch):
    import radar
    with open(tmp_path / "aziende.json", "w") as f:
        json.dump([{"nome": "Boutique", "settore": "Boutique", "url": "https://boutique.example/lavora-con-noi"}], f)
    # aziende.json può contenere solo nome e url: il tipo di sito viene riconosciuto (qui una pagina generica)
    visti = []

    def finto_leggi(fonte, paesi, chiavi=None):
        visti.append(fonte["tipo"])
        return [fonti._annuncio("p:1", "Graduate Program 2027", "Milano", "https://x/1", descrizione="Testo completo")]
    monkeypatch.setattr(fonti, "leggi", finto_leggi)
    r = Radar(str(tmp_path))
    r.scansiona()
    radar.crea_sito(r, str(tmp_path / "sito"))
    assert visti == ["pagina"]
    dati = json.loads((tmp_path / "sito" / "dati.json").read_text())
    assert [o["titolo"] for o in dati] == ["Graduate Program 2027"]
    assert "stato" not in dati[0] and "note" not in dati[0]  # i dati personali non finiscono sul sito
    assert "descrizione" not in dati[0] and not (tmp_path / "sito" / "descrizioni.json").exists()
    assert "Testo completo" not in "".join(f.read_text() for f in (tmp_path / "sito").iterdir() if f.is_file())
    pagina = (tmp_path / "sito" / "index.html").read_text()
    assert "window.RADAR_STATICO = true" in pagina and 'content="noindex' in pagina
    assert json.loads((tmp_path / "sito" / "stato.json").read_text())["fonti"][0]["stato"]["ok"] == 1


class FintoSMTP:
    inviati = []
    rompi = False

    def __init__(self, host, porta, timeout=None):
        self.host = host

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def login(self, utente, password):
        if FintoSMTP.rompi:
            raise OSError("server non raggiungibile")

    def send_message(self, msg):
        FintoSMTP.inviati.append(msg)


def test_email_solo_per_le_novita(tmp_path, monkeypatch):
    import smtplib
    FintoSMTP.inviati = []
    monkeypatch.setattr(smtplib, "SMTP_SSL", FintoSMTP)
    monkeypatch.setenv("EMAIL_UTENTE", "io@example.com")
    monkeypatch.setenv("EMAIL_PASSWORD", "password-app")
    with open(tmp_path / "aziende.json", "w") as f:
        json.dump([{"nome": "Banca Test", "settore": "Banca", "tipo": "finta", "attiva": True}], f)
    elenco = [fonti._annuncio("t:1", "Summer Analyst 2027", "Milano", "https://x/1")]
    monkeypatch.setattr(fonti, "leggi", lambda fonte, paesi, chiavi=None: list(elenco))
    r = Radar(str(tmp_path))

    r.scansiona()  # prima scansione: niente email per gli annunci già esistenti
    assert FintoSMTP.inviati == []

    elenco += [fonti._annuncio("t:2", "Off-cycle Intern - M&A", "London", "https://x/2"),
               fonti._annuncio("t:3", "Junior - Categorie Protette - Audit", "Milano", "https://x/3"),
               fonti._annuncio("t:4", "Analyst", "Milano", "https://x/4")]  # "da verificare": niente email
    FintoSMTP.rompi = True
    r.scansiona()  # server email irraggiungibile: si riprova al giro dopo
    assert FintoSMTP.inviati == []
    FintoSMTP.rompi = False
    r.scansiona()
    assert len(FintoSMTP.inviati) == 1
    msg = FintoSMTP.inviati[0]
    assert msg["Subject"] == "🎯 Banca Test: Off-cycle Intern - M&A" and msg["To"] == "io@example.com"
    corpo = msg.get_payload()[1].get_payload(decode=True).decode()
    assert "https://x/2" in corpo and "Off-cycle" in corpo and "Protette" not in corpo
    r.scansiona()  # già segnalata: nessun doppione
    assert len(FintoSMTP.inviati) == 1


def test_archivio_vecchio_senza_colonna_notificata(tmp_path):
    import sqlite3
    from archivio import Archivio
    db = sqlite3.connect(tmp_path / "radar.db")
    db.execute("CREATE TABLE offerte (id TEXT PRIMARY KEY, azienda TEXT, settore TEXT, fonte TEXT, titolo TEXT, "
               "luogo TEXT, paese TEXT, url TEXT, pubblicata TEXT, prima_vista TEXT, ultima_vista TEXT, "
               "attiva INTEGER DEFAULT 1, categorie TEXT DEFAULT '[]', rilevanza INTEGER DEFAULT 0, "
               "descrizione TEXT DEFAULT '', nuova INTEGER DEFAULT 0, letta INTEGER DEFAULT 0, "
               "stato TEXT DEFAULT '', note TEXT DEFAULT '')")
    db.commit()
    db.close()
    assert Archivio(str(tmp_path / "radar.db")).da_notificare(2) == []


def test_oggetto_email_con_piu_posizioni():
    import notifiche
    offerte = [{"azienda": a, "titolo": "Graduate", "categorie": ["graduate"], "luogo": "", "url": ""}
               for a in ["JPMorgan", "Deloitte", "JPMorgan", "Citi", "PwC"]]
    assert notifiche.oggetto(offerte) == "🎯 5 nuove posizioni: JPMorgan, Deloitte, Citi e altre 1"


def test_senza_email_niente_invio_di_massa_dopo(tmp_path, monkeypatch):
    import smtplib
    FintoSMTP.inviati, FintoSMTP.rompi = [], False
    monkeypatch.setattr(smtplib, "SMTP_SSL", FintoSMTP)
    with open(tmp_path / "aziende.json", "w") as f:
        json.dump([{"nome": "Banca Test", "tipo": "finta", "attiva": True}], f)
    elenco = [fonti._annuncio("t:1", "Summer Analyst 2027", "Milano", "https://x/1")]
    monkeypatch.setattr(fonti, "leggi", lambda fonte, paesi, chiavi=None: list(elenco))
    r = Radar(str(tmp_path))
    r.scansiona()
    elenco.append(fonti._annuncio("t:2", "Graduate Program", "Milano", "https://x/2"))
    r.scansiona()  # email non ancora configurata: t:2 resta solo nel terminale
    monkeypatch.setenv("EMAIL_UTENTE", "io@example.com")
    monkeypatch.setenv("EMAIL_PASSWORD", "x")
    r.scansiona()
    assert FintoSMTP.inviati == []  # niente invio di massa delle posizioni arretrate
    elenco.append(fonti._annuncio("t:3", "Off-cycle Intern", "Milano", "https://x/3"))
    r.scansiona()
    assert len(FintoSMTP.inviati) == 1 and "Off-cycle" in FintoSMTP.inviati[0]["Subject"]
