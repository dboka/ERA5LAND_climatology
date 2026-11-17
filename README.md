# Pasaules klimats

Interaktīva gaisa temperatūras un nokrišņu anomāliju karte 195 ANO dalībvalstīm un novērotājvalstīm. Vietne izmanto Copernicus ERA5-Land valstu dienu datus un salīdzina izvēlēto periodu ar 1991–2020 klimatisko normu. Frontend: React, TypeScript, MapLibre GL JS. API: FastAPI. Glabāšana: PostgreSQL/PostGIS Docker volume.

## Pašreizējais stāvoklis

Vēsturiskais temperatūras un nokrišņu ARCO Zarr imports ir **pabeigts**. PostGIS glabā pilnu 1991–2020 valstu dienu vēsturi, 366 kalendāra dienu normas un 2020+ dienas abiem rādītājiem. Temperatūras un nokrišņu dienas lokāli tiek papildinātas automātiski; 2026. gada 17. novembrī abi arhīvi ir atjaunoti līdz jaunākajai ARCO pilnajai dienai **2026-11-08**. 188 valstīm ir abu rādītāju dati; 7 salu valstīm ERA5-Land sauszemes režģa pārklājums nav pietiekams, tāpēc tās kartē redzamas ar statusu “Nav datu”. Monako un Vatikāns ir atsevišķi marķētas reģionālas aproksimācijas.

Precīza failu un Docker volume karte, tabulu saturs un rezerves kopijas instrukcija: [DATA_STORAGE.md](DATA_STORAGE.md). Ikdienas plūsma un GitHub Pages ceļš: [AUTOMATION.md](AUTOMATION.md). Aprēķinu un robežu metodika: [ARCHITECTURE.md](ARCHITECTURE.md).

## Atvērt lokāli

Nepieciešams palaists Docker Desktop, Node.js, Python virtuālā vide `.venv`, instalētas atkarības un projekta `.env` ar `CLIMATE_DB_PASSWORD`. Pirmajā reizē:

```powershell
cd C:\Users\deniss.boka\Desktop\Global_TEMP_Copernicus\PROJECT_EUROPE
npm install
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements-arco.txt
Copy-Item .env.example .env
```

`.env` veidnē nomainiet paroli pret lokālās PostGIS datubāzes paroli; ja DB jau darbojas, saglabājiet tās esošo paroli. Ikdienas ARCO importam nepieciešama arī CDS API piekļuve un pieņemti ERA5-Land piekļuves noteikumi. Pēc tam:

```powershell
.\scripts\start_local_site.ps1
```

Vietne: **http://127.0.0.1:5173/**. API metadati: **http://127.0.0.1:8013/api/meta**. API dokumentācija: **http://127.0.0.1:8013/docs**. Skripts nepieļauj demonstrācijas datu uzdošanu par ERA5-Land un atsakās startēt, ja DB režīms nav `era5_land`.

## Kā lietot

Augšā izvēlieties **Temperatūra** vai **Nokrišņi**, pēc tam dienu, nedēļu, intervālu, mēnesi, meteoroloģisko sezonu vai gadu. Temperatūras karte rāda anomāliju °C skalā −6…+6 °C. Nokrišņu karte rāda perioda summas procentuālo novirzi no normas, brūnā krāsā sausākus un zilā mitrākus periodus; profilā faktiskā un normas summa ir milimetros. Uzvediet peli, lai redzētu vērtību; klikšķiniet uz valsts, lai redzētu summu vai vidējo, normu un dinamiku. Mazās valstis var atlasīt ar kartes punktu vai meklēšanu. CSV eksportē atlasītā perioda valstu rezultātus. Septiņas valstis bez datiem var meklēt un atvērt, bet tām netiek rādīti izdomāti skaitļi. Grenlande un citas ārpus 195 valstu saraksta esošās teritorijas redzamas neitrālā, neklikšķināmā slānī.

## Datu plūsma

`backend/etl/arco_backfill.py` apstrādāja 1991–2025 trūkstošās temperatūras UTC dienas no ERA5-Land ARCO Zarr. Agrākās 1991-01–1994-11 dienas jau bija saglabātas no CDS dienas statistikas. `backend/etl/arco_2026.py` apstrādāja 2026. gadu. `backend/etl/arco_precipitation.py` no cita ERA5-Land Zarr avota sagatavoja nokrišņu vēsturisko arhīvu līdz 2026-11-03; jaunākās dienas pievieno `backend/etl/arco_precip_daily_update.py`. Režģa un valstu ģeometriju platību svari tiek kešoti `data/weights-*.npz`; katra pabeigtā diena tiek saglabāta PostGIS. Pilni ERA5-Land režģi netiek arhivēti. Abiem rādītājiem ir 1991–2020 vēsture un normas, kā arī 2020+ dienas. 2020. gads apzināti ietilpst abās dienu tabulās. Lietotāja pieprasījums **nekad nelejupielādē ERA5-Land**; FastAPI nolasa sagatavotās valstu tabulas.

Lokālais Windows uzdevums `GlobalClimateDailyUpdate` strādā katru dienu plkst. 08.00 un pēc lietotāja pieteikšanās. Tas izmanto `backend/etl/arco_daily_update.py` temperatūrai un `backend/etl/arco_precip_daily_update.py` nokrišņiem, PostGIS izmanto kā kontrolpunktu un atjauno `public/data/` un statisko `dist/` būvējumu. Statuss:

```powershell
.\scripts\daily_update_status.ps1
```

Pirmais automātiskās plūsmas cikls veiksmīgi papildināja datus no 2026-10-22 līdz 2026-11-03. Importeris nav ierobežots ar 2026. gadu, tomēr jaunās dienas parādīsies tikai pēc ARCO publikācijas. Vecais `arco_2026.py` paliek vēsturiskā izmēģinājuma kods; ikdienas uzdevums to vairs neizsauc. Vecais CDS uzdevums `GlobalClimateERA5Resume` ir atspējots. Skatīt [AUTOMATION.md](AUTOMATION.md) par kļūdu atsākšanu, grafiku un manuālo pārbaudi.

## Statisks eksports, piemēram, GitHub Pages

Ja vajadzīga vietne bez dzīva API, no pašreizējās PostGIS datubāzes var ģenerēt mēnešu JSON momentuzņēmumu:

```powershell
. .\scripts\postgis-env.ps1
.\.venv\Scripts\python.exe -m backend.export_static
$env:VITE_STATIC_DATA='1'
$env:GITHUB_PAGES='1'
npm run build
```

`dist/` ir gatavs statisks būvējums. GitHub Pages izmanto repozitorijā iekļauto `public/data/` momentuzņēmumu; `.github/workflows/pages.yml` tiek palaista tikai manuāli. `vite.config.ts` nosaka bāzes ceļu no `GITHUB_REPOSITORY` vai `PAGES_BASE`. GitHub Pages pats nevar palaist Python ETL vai piekļūt šī datora PostGIS. Lokālais ikdienas uzdevums turpina gatavot jaunos datus, bet neko automātiski nesūta uz GitHub; skatīt [AUTOMATION.md](AUTOMATION.md).

## API un pārbaudes

- `GET /api/meta?metric=precipitation` — nokrišņu datu periods, valstu skaits, izcelsme.
- `GET /api/anomalies?start=2026-09-01&end=2026-09-30&metric=precipitation` — perioda faktiskā nokrišņu summa mm, normas summa mm un novirze % pa valstīm.
- `GET /api/countries/LVA/series?start=2026-09-01&end=2026-09-30&metric=precipitation` — Latvijas dienu dinamika.
- Bez `metric` parametra API atgriež iepriekšējo temperatūras skatu.
- `npm run build` — TypeScript pārbaude un produkcijas būvējums.
- `.\.venv\Scripts\python.exe -m unittest discover -s tests -v` — ETL, garā gada un valstu kataloga pārbaudes.

Valstu latviskie nosaukumi ir no Unicode CLDR, karogi ir lokālas `flag-icons` SVG kopijas (`public/flags/LICENSE`), robežas — Natural Earth. ERA5-Land avots: [Copernicus Climate Data Store](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-land?tab=overview). Vietne ir lokāls projekta prototips; LVĢMC logotipa izmantošana šajā prototipā pati par sevi nenozīmē oficiālu publikāciju.
