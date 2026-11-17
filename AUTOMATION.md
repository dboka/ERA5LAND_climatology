# Ikdienas datu atjaunināšana

Lokālā plūsma ir ieslēgta 2026-11-09. Windows uzdevums `GlobalClimateDailyUpdate` startē **katru dienu plkst. 08.00 pēc datora vietējā laika** un lietotājam piesakoties sistēmā. Kopš 2026-11-17 tas papildina gan temperatūru, gan nokrišņus. ARCO pieejamība nosaka faktisko jaunāko dienu; nav pieņēmuma, ka vakardienas dati jau ir publicēti.

## Katrs cikls

`scripts/run_daily_update.ps1`:

1. Sagaida Docker Desktop (līdz 15 minūtēm) un PostGIS (līdz 5 minūtēm), tad pārbauda vai palaiž lokālo FastAPI un Vite vietni.
2. `backend/etl/arco_daily_update.py` no DB nosaka nākamo UTC dienu, no ARCO metadatiem nosaka pēdējo **pilno** dienu, pārbauda 24 stundas un 188 valstu vērtības un katru dienu ieraksta atsevišķā DB transakcijā. 1991–2020 vēsturi un normas tas nemaina. Īslaicīgas tīkla, ARCO limita un DB kļūdas tiek atkārtotas ar pauzi līdz 30 minūtēm. Pastāvīga kļūda aptur ciklu; nākamais mēģinājums turpina no DB kontrolpunkta.
3. `backend/etl/arco_precip_daily_update.py` ar tādu pašu pilnas UTC dienas, 188 valstu un PostGIS kontrolpunkta pārbaudi papildina `precipitation_daily`; 1991–2020 normas tas nemaina.
4. Pēc abiem importiem `backend/export_static.py` atjauno temperatūras un nokrišņu `public/data/` JSON momentuzņēmumus.
5. Vite ar `VITE_STATIC_DATA=1` un `GITHUB_PAGES=1` pārbūvē `dist/` statiskajai izvietošanai.

Lokālā vietne `http://127.0.0.1:5173/` izmanto dzīvu FastAPI/PostGIS savienojumu, tāpēc jaunās dienas ir redzamas bez manuāla eksporta. Atvērta lapa pārbauda jaunāko datumu ik pēc piecām minūtēm un, atgriežoties pie cilnes vai loga, uzreiz. Statiskā vietne izmanto `public/data/` momentuzņēmumu; pēc jaunas GitHub Pages versijas publicēšanas atvērta cilne pārlādējas, kad pamana jaunu datumu.

Uzdevumam ir `StartWhenAvailable`, atkārtota palaišana pēc kļūdas (3 reizes ar 30 minūšu intervālu), nav izpildes laika limita un tas drīkst strādāt ar akumulatoru. Vienlaikus drīkst darboties tikai viens ieplānots cikls; Python izmanto arī PostGIS advisory lock. **Izslēgts dators pats nevar lejupielādēt datus.** Pēc ieslēgšanas un pieteikšanās logon trigeris papildina visas pa to laiku ARCO pieejamās pilnās dienas. Vecais 15 minūšu CDS uzdevums `GlobalClimateERA5Resume` paliek atspējots.

## Pārbaude un manuāla vadība

PowerShell projekta saknē:

```powershell
.\scripts\daily_update_status.ps1
. .\scripts\postgis-env.ps1
.\.venv\Scripts\python.exe -m backend.etl.arco_daily_update --probe
.\.venv\Scripts\python.exe -m backend.etl.arco_precip_daily_update --probe
Start-ScheduledTask -TaskName GlobalClimateDailyUpdate
```

Pēdējās palaišanas žurnāls ir `data/logs/daily-update-YYYYMMDD-HHMMSS.log`; datubāze paliek Docker volume `project_europe_climate_pgdata`. `daily_update_status.ps1` rāda Task Scheduler rezultātu, PostGIS pēdējo dienu un statiskā eksporta pēdējo dienu. `result 0` nozīmē veiksmīgu ciklu; `267009` nozīmē, ka uzdevums vēl darbojas. Atkārtota palaišana saglabā jau ierakstītās dienas un turpina ar nākamo.

Vienu kontrolētu dienu var apstrādāt ar `python -m backend.etl.arco_daily_update --max-days 1`; `--through-date YYYY-MM-DD` ierobežo pēdējo dienu. `--probe` veic tikai ARCO metadatu un DB pārbaudi, neko neraksta. Importerī nav 2026. gada robežas, tādēļ tas var turpināt 2027. gadā, ja ARCO publicē stundas tajā pašā datu kopā un režģis nemainās. Režģa vai valstu pārklājuma izmaiņas tiek noraidītas, nevis klusi sajauktas ar iepriekšējiem rezultātiem.

## GitHub Pages ceļš

Publiskais repozitorijs ir `dboka/ERA5LAND_climatology`. Tajā ir tikai pārskatīts pirmkods, kartes robežas, karogi un `public/data/` valstu dienu temperatūru, nokrišņu un normu **statisks momentuzņēmums**. `data/`, `.env`, pilnie ERA5-Land režģi, žurnāli un PostgreSQL volume netiek komitēti. Pārlūks GitHub Pages vidē aprēķina izvēlētā perioda anomāliju no publiskajiem JSON, neizmantojot dzīvu datubāzes savienojumu.

`.github/workflows/pages.yml` sākas tikai ar manuālu `workflow_dispatch`. Kodam un datiem piesūtītas izmaiņas pašas vietni neizvieto. Lokālais `GlobalClimateDailyUpdate` turpina atjaunot PostGIS, `public/data/` un `dist/`, bet **neveic Git commit, push vai GitHub izvietošanu**. Nākamo publisko versiju varēs izvietot atsevišķi pēc pārskatīšanas. GitHub Pages nevar pats izpildīt Python ETL vai piekļūt lokālajam PostGIS. Nākotnes servera izvietojumā API un PostgreSQL būs atsevišķa infrastruktūra.

Oficiālais [GitHub Pages pielāgotu darbplūsmu apraksts](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages) nosaka `configure-pages`, `upload-pages-artifact`, `deploy-pages` darbības un `pages: write` / `id-token: write` atļaujas; tās ir iekļautas šī projekta darbplūsmā.
