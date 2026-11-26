# Radar Carriere: stage, summer internship, graduate program e posizioni junior

Ti manda un'**email appena esce una posizione nuova** in banche, Big Four, società di consulenza,
asset manager e trading firm. Così ti candidi tra i primi. Controlla le aziende **ogni 20 minuti**,
dalle 7 alle 23, anche quando il PC è spento.

Sul tuo PC c'è anche un **terminale privato** in stile Bloomberg per sfogliare tutte le posizioni aperte,
leggere gli annunci, salvarli e tenere traccia delle candidature. È visibile solo a te.

**Cosa cerca**
- **Summer internship** e **off-cycle** (anche spring/autumn internship)
- **Stage / tirocini** (internship, stage, tirocinio, Praktikum, stagiaire, placement…)
- **Graduate program** (graduate scheme, analyst program, neolaureati, early careers, trainee…)
- **Junior / entry level**, anche quando il titolo non dice "stage". Esempio Deloitte: il titolo è
  "Junior Consultant", ma la descrizione dice che la posizione è aperta a stagisti e neolaureati.
  Il radar legge anche la descrizione e lo riconosce.
- Scarta da solo i ruoli senior (Manager, VP, Director, "5+ years of experience"…).

## 1. Le email (5 minuti, una volta sola)

Serve una **password per le app** di Gmail: è diversa dalla tua password normale e serve solo a
questo programma per inviarti le email.

1. Attiva la **verifica in due passaggi** sul tuo account Google, se non l'hai già fatto
   (<https://myaccount.google.com/security>).
2. Apri <https://myaccount.google.com/apppasswords>, scrivi un nome (es. `Radar Carriere`) e premi **Crea**.
   Copia la password di 16 lettere che compare.
3. Su questo repository vai in **Settings → Secrets and variables → Actions → New repository secret**
   e crea:
   - `EMAIL_UTENTE`: il tuo indirizzo Gmail;
   - `EMAIL_PASSWORD`: la password per le app del punto 2.

   Facoltativo: `EMAIL_DESTINATARIO`, se vuoi ricevere le email su un altro indirizzo.
4. Vai in **Actions → Radar Carriere → Run workflow** per un primo controllo.

Da quel momento ricevi un'email ogni volta che compare una posizione nuova. L'oggetto contiene azienda
e ruolo. Nell'email trovi tipo (summer, off-cycle, stage, graduate, junior), luogo e un pulsante
**CANDIDATI** che porta all'annuncio.

- Ricevi solo le posizioni **nuove**: quelle già pubblicate quando il radar ha iniziato a controllare
  un'azienda non vengono inviate.
- Le posizioni riservate alle categorie protette (L. 68/99) e quelle "da verificare" (titoli generici
  come "Analyst") non vengono inviate. Le vedi comunque nel terminale sul PC.
- I secrets sono cifrati: nessuno, nemmeno chi visita il repository, può leggerli.
- Il repository è pubblico perché così GitHub non pone limiti ai minuti di controllo. Contiene solo il
  codice: nessun annuncio, nessun dato tuo. Nei registri dei controlli compare solo il numero di
  posizioni trovate.

## 2. Il terminale privato sul PC (facoltativo)

1. Installa **Python** (3.10 o successivo) da <https://www.python.org/downloads/>.
   ⚠️ Nella prima schermata spunta **"Add python.exe to PATH"**.
2. Scarica questo repository (**Code → Download ZIP**) ed estrailo.
3. Fai **doppio clic su `radar/avvia.bat`**: si apre una finestra nera (lasciala aperta) e il browser su
   <http://127.0.0.1:8777>. Su Mac/Linux: `python3 radar/radar.py`.

> **Errore "certificate has expired" in F2?** Su alcuni PC Windows l'archivio dei certificati di sistema
> contiene certificati vecchi. `avvia.bat` installa da solo, la prima volta, il pacchetto `certifi`
> (l'elenco aggiornato dei certificati di Mozilla) e il radar lo usa al posto di quello di Windows.
> Se l'errore restasse: apri il Prompt dei comandi e scrivi `python -m pip install certifi`.

Il terminale funziona solo sul tuo computer: nessun altro può aprirlo. Ha un suo archivio, separato da
quello delle email.

| Tasto o comando | Cosa fa |
|---|---|
| **F1 / F2 / F3 / F4** | Posizioni, Aziende monitorate, Impostazioni, Registro |
| scrivi nella barra `RADAR>` | cerca ovunque (es. `deloitte milano audit`) |
| `/summer` `/offcycle` `/stage` `/graduate` `/junior` | filtra per tipo |
| `/nuove` `/salvate` `/candidature` `/tutte` | cambia vista |
| `/it` `/uk` | solo Italia / solo Regno Unito |
| `/scan` | controlla subito tutte le aziende |
| `j` `k` (o le frecce) | scorri le posizioni |
| `Invio` | apri l'annuncio per candidarti |
| `s` `c` `x` | salva, segna "mi sono candidato", scarta |

## Aziende incluse

**117 aziende** controllate automaticamente: abrdn, Accenture, AIG, AlixPartners, AllianceBernstein, Alvarez & Marsal, Analysis Group, Ardian, Aurelius, Avison Young, Aviva Investors, Bain & Company, Bain Capital, Bank of America, Barclays, Barings, BBVA, Bip, BlackRock, BMO, BNY Mellon, Boston Consulting Group, BP Trading, British Land, Brookfield Asset Management, Cambridge Associates, Canary Wharf Group, Capital Group, Capital One, Capstone, Capza, Citi, Clearwater International, Colliers, Compass Lexecon, Crédit Agricole CIB, Cushman & Wakefield, Dare, Deloitte, Deutsche Bank, DRW, EY, Forvis Mazars, Franklin Templeton, General Atlantic, Glencore, Goldman Sachs, GP Bullhound, Grosvenor Group, GSA Capital, Houlihan Lokey, HSBC, Huron, IMC Trading, ING, Jane Street, JLL, JPMorgan Chase, Jump Trading, Jupiter Asset Management, Knight Frank, KPMG UK, Landsec, Lazard, Legal & General, Lichfields, Lincoln International, Lloyds Banking Group, Mako Trading, Man Group, Marshall Wace, Mastercard, Maven Securities, Millennium Management, Mizuho, Moelis & Company, Montagu Evans, Morgan Stanley, MUFG, Mutares, NatWest Markets, Oliver Wyman / Marsh McLennan, Optiver, Oxera, PA Consulting, PGIM, Pictet, PIMCO, Piper Sandler, PJT Partners, Point72, Protiviti, PSP Investments, PwC, Raymond James, RBC Capital Markets, Roland Berger, Rothschild & Co, S&P Global, Santander, Schroders, Sculptor Capital, Shell, Squarepoint Capital, State Street, Stifel, T. Rowe Price, TD Securities, Tikehau Capital, Tower Research Capital, Triton Partners, Turner & Townsend, UniCredit, Vanguard, Wellington Management, William Blair, Winton Capital.

Altre aziende dell'elenco (molte boutique italiane, Mediobanca, Banco BPM, Intesa Sanpaolo, UBS, Nomura, Jefferies, Evercore, Commerzbank…) pubblicano solo su LinkedIn o su pagine che si caricano con JavaScript e non si possono leggere in automatico: il file `radar/scoperta/elenco.json` le contiene tutte, e lo strumento **Actions → Scoperta aziende** permette di ricontrollarle in futuro.

**Aggiungere un'azienda per le email**: apri `radar/aziende.json`, premi la matita ✎ e aggiungi
prima dell'ultima `]` una riga così, con la virgola dopo la voce precedente:

```json
{"nome": "Mediobanca", "settore": "Banca d'investimento", "url": "https://indirizzo-della-pagina-carriere"}
```

Come `url` incolla l'indirizzo della pagina con l'elenco delle posizioni aperte. Il radar riconosce
da solo Workday (`…myworkdayjobs.com`), Greenhouse, Lever, SmartRecruiters, Ashby, Oracle e Avature.
Per le pagine "fatte in casa", tipiche delle boutique, legge i link che sembrano annunci di stage,
graduate o junior. Nel terminale sul PC puoi aggiungere un'azienda anche dalla scheda **F2**, che
prova subito se riesce a leggerla.

**EY, KPMG, Goldman Sachs, McKinsey, BCG, Bain, Mediobanca, Intesa, UniCredit, Generali…** non hanno
un sito leggibile direttamente. Per coprirle c'è **Adzuna**, un aggregatore di annunci con chiave gratuita:
registrati su <https://developer.adzuna.com/signup>, poi crea i secrets `ADZUNA_APP_ID` e `ADZUNA_APP_KEY`.
Dal controllo successivo la fonte si attiva da sola.

## Paesi

Di default cerca in **tutta Italia**, a **Londra** e a **Parigi**: il resto del mondo è escluso (anche
Manchester, Lione, ecc.). Per cambiarli: **Settings → Secrets and variables → Actions → Variables → New
repository variable**, con nome `RADAR_PAESI` e valore, per esempio, `IT,LON,PAR,IE`.
Codici: `LON` (solo Londra), `PAR` (solo Parigi), oppure paesi interi: IT, GB, IE, FR, DE, CH, LU, NL, BE, ES…

## Buone maniere e limiti

- Il radar si presenta ai siti con un nome riconoscibile. Se un sito risponde "troppe richieste"
  (HTTP 429), quella fonte salta il giro e riprova al successivo: gli annunci non si perdono.
- GitHub non garantisce l'orario esatto dei controlli programmati: a volte partono con qualche minuto
  di ritardo.
- Se il repository resta senza attività per 60 giorni, GitHub sospende i controlli programmati:
  ti avvisa via email e basta riattivarli dalla scheda Actions.
- Il riconoscimento del tipo di posizione si basa su parole chiave in italiano, inglese, francese,
  tedesco e spagnolo. È affidabile ma non perfetto: prima di candidarti, leggi sempre l'annuncio.

| File | Contenuto |
|---|---|
| `radar/radar.py` | avvio (`python radar.py` terminale, `scansiona` un controllo, `prova URL`) |
| `radar/fonti.py` | lettori dei siti carriere (Workday, Greenhouse, Oracle, Avature, …) |
| `radar/classifica.py` | riconoscimento di stage/summer/graduate/junior e dei paesi |
| `radar/motore.py`, `radar/archivio.py` | controllo e archivio (SQLite) |
| `radar/notifiche.py` | le email |
| `radar/web/index.html` | il terminale |
| `radar/aziende.json` | elenco delle aziende monitorate |
| `.github/workflows/radar.yml` | controllo ogni 20 minuti |

Test: `python -m pytest radar`
