# Radar Carriere: stage, summer internship, graduate program e posizioni junior

Un sito in stile terminale che **si aggiorna da solo ogni ora** con le posizioni aperte di banche,
Big Four, società di consulenza, asset manager e trading firm, filtrate per chi sta finendo la magistrale.
Lo apri da PC o telefono, senza installare niente: **https://simones-ai.github.io/radar-carriere/**

**Cosa cerca**
- **Summer internship** e **off-cycle** (anche spring/autumn internship)
- **Stage / tirocini** (internship, stage, tirocinio, Praktikum, stagiaire, placement…)
- **Graduate program** (graduate scheme, analyst program, neolaureati, early careers, trainee…)
- **Junior / entry level**, anche quando il titolo non dice "stage". Esempio Deloitte: il titolo è
  "Junior Consultant", ma la descrizione dice che la posizione è aperta a stagisti e neolaureati.
  Il radar legge anche la descrizione e lo riconosce.
- Scarta da solo i ruoli senior (Manager, VP, Director, "5+ years of experience"…).

## Come funziona

Ogni ora, dalle 7 alle 23 circa, GitHub (gratis) esegue il radar: legge i siti carriere, classifica
gli annunci e ripubblica il sito. Il tuo PC può restare spento.

Sul sito:
- le posizioni comparse dopo la tua prima visita e non ancora aperte sono segnate **● NUOVE**;
- per ogni posizione puoi **salvarla**, segnarla **"mi sono candidato"**, **scartarla** e scrivere **note**;
- salvate, candidature e note restano **solo nel tuo browser**. Per passarle dal PC al telefono usa
  **F3 → Esporta / Importa**.

**Cosa c'è (e cosa non c'è) sul sito pubblico**: solo titolo, azienda, luogo, data, tipo di posizione e
il link all'annuncio originale. I testi completi degli annunci non vengono ripubblicati, perché sono delle
aziende e possono contenere nomi e contatti dei recruiter. Il radar li legge solo durante la scansione,
per capire se una posizione "Junior" è aperta a stagisti. Il sito chiede ai motori di ricerca di non
indicizzarlo (`noindex`), quindi lo trova solo chi ha il link.

| Tasto o comando | Cosa fa |
|---|---|
| **F1 / F2 / F3 / F4** | Posizioni, Aziende monitorate, I miei dati, Registro |
| scrivi nella barra `RADAR>` | cerca ovunque (es. `deloitte milano audit`) |
| `/summer` `/offcycle` `/stage` `/graduate` `/junior` | filtra per tipo |
| `/nuove` `/salvate` `/candidature` `/tutte` | cambia vista |
| `/it` `/uk` | solo Italia / solo Regno Unito |
| `j` `k` (o le frecce) | scorri le posizioni |
| `Invio` | apri l'annuncio per candidarti |
| `s` `c` `x` | salva, segna "mi sono candidato", scarta |

## Messa in funzione (una volta sola, 3 minuti)

1. Sul repository vai in **Settings → Pages** e, alla voce **Source**, scegli **GitHub Actions**.
2. Vai in **Actions**. Se GitHub lo chiede, premi il pulsante verde per abilitare i workflow.
   Poi apri **Radar Carriere → Run workflow → Run workflow**.
3. Dopo qualche minuto (il primo giro legge tutti gli annunci già pubblicati) il sito è online
   all'indirizzo qui sopra. Da lì in poi si aggiorna da solo.

## Aziende incluse

Deloitte (portale Italia, Grecia e Malta), PwC, Accenture, Oliver Wyman/Marsh McLennan, JPMorgan,
Morgan Stanley, Citi, Deutsche Bank, Barclays, Bank of America, BlackRock, State Street, S&P Global,
Mastercard, Point72, Jane Street, IMC, Squarepoint, Jump Trading, Tower Research, DRW e General Atlantic.

**Aggiungere un'azienda**: apri `radar/aziende.json`, premi la matita ✎ e aggiungi prima dell'ultima `]`
una riga così, con la virgola dopo la voce precedente:

```json
{"nome": "Mediobanca", "settore": "Banca d'investimento", "url": "https://indirizzo-della-pagina-carriere"}
```

Come `url` incolla l'indirizzo della pagina con l'elenco delle posizioni aperte. Il radar riconosce
da solo Workday (`…myworkdayjobs.com`), Greenhouse, Lever, SmartRecruiters, Ashby, Oracle e Avature.
Per le pagine "fatte in casa", tipiche delle boutique, legge i link che sembrano annunci di stage,
graduate o junior.
Dopo il *Commit changes* il sito si aggiorna in pochi minuti. In **F2** vedi se l'azienda è letta
correttamente (pallino verde) o perché no (pallino rosso).

**EY, KPMG, Goldman Sachs, McKinsey, BCG, Bain, Mediobanca, Intesa, UniCredit, Generali…** non hanno
un sito leggibile direttamente. Per coprirle c'è **Adzuna**, un aggregatore di annunci con chiave gratuita:
1. registrati su <https://developer.adzuna.com/signup>;
2. nel repository vai in **Settings → Secrets and variables → Actions → New repository secret** e crea
   `ADZUNA_APP_ID` e `ADZUNA_APP_KEY`.

Dal giro successivo la fonte si attiva da sola. Tiene solo le aziende dell'elenco `solo_aziende` in
`radar/aziende.json`, che puoi modificare.

## Paesi

Di default cerca in **Italia** e **Regno Unito**. Per cambiarli: **Settings → Secrets and variables →
Actions → Variables → New repository variable**, con nome `RADAR_PAESI` e valore, per esempio, `IT,GB,IE,FR,DE,CH`.
Codici disponibili: IT, GB, IE, FR, DE, CH, LU, NL, BE, ES, PT, GR, MT, PL, AE, US, SG, HK, IN.

## Buone maniere e limiti

- Il radar si presenta ai siti con un nome riconoscibile e fa al massimo una scansione all'ora. Se un
  sito risponde "troppe richieste" (HTTP 429), quella fonte salta il giro e riprova al successivo:
  gli annunci non si perdono. Lo stato di ogni fonte è in **F2**.
- I server di GitHub sono condivisi, quindi alcuni siti Workday potrebbero rispondere spesso "troppe richieste".
- Se il repository resta senza attività per 60 giorni, GitHub sospende i workflow programmati:
  basta riattivarlo dalla scheda Actions.
- Il riconoscimento del tipo di posizione si basa su parole chiave in italiano, inglese, francese,
  tedesco e spagnolo. È affidabile ma non perfetto: prima di candidarti, leggi sempre l'annuncio.

## Usarlo anche sul PC (facoltativo)

Lo stesso programma funziona anche in locale, con aggiunta di aziende e impostazioni direttamente
dall'interfaccia: installa Python (spuntando "Add python.exe to PATH") e fai doppio clic su
`radar/avvia.bat`. Su Mac/Linux: `python3 radar/radar.py`. Non servono librerie esterne.

| File | Contenuto |
|---|---|
| `radar/radar.py` | avvio (`python radar.py`, `scansiona`, `sito CARTELLA`, `prova URL`) |
| `radar/fonti.py` | lettori dei siti carriere (Workday, Greenhouse, Oracle, Avature, …) |
| `radar/classifica.py` | riconoscimento di stage/summer/graduate/junior e dei paesi |
| `radar/motore.py`, `radar/archivio.py` | scansione e archivio (SQLite) |
| `radar/web/index.html` | il terminale (lo stesso per il sito e per il PC) |
| `radar/aziende.json` | elenco delle aziende monitorate |
| `.github/workflows/sito.yml` | aggiornamento orario e pubblicazione su GitHub Pages |

Test: `python -m pytest radar`
