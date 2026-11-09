# Datu glabāšana un atjaunošana

Šis dokuments apraksta lokālo instalāciju 2026. gada 9. novembrī. Projekta sakne ir `C:\Users\deniss.boka\Desktop\Global_TEMP_Copernicus\PROJECT_EUROPE`. Datu stāvokli jebkurā brīdī var pārbaudīt ar `scripts\daily_update_status.ps1` un API `http://127.0.0.1:8013/api/meta`.

## Kur atrodas dati

| Vieta | Saturs | Vai tas ir galvenais avots? |
| --- | --- | --- |
| Docker volume `project_europe_climate_pgdata` | PostgreSQL 16 / PostGIS 3.6 datubāze `climate`: visas valstu dienas, 1991–2020 vēsture un normas | **Jā** |
| `data/weights-*.npz` | Režģa šūnu un valstu ģeometriju platību svaru kešs | Nē; no robežām un režģa to var veidot atkārtoti |
| `data/logs/` | ARCO, API un vietnes procesa žurnāli un PID faili | Nē |
| `data/arco-2026-days.jsonl` | 2026. gada importa dienu kontrolpunktu žurnāls | Nē; faktiskās vērtības ir PostGIS |
| `data/raw/`, `data/pilot_raw/` | Iepriekšējo CDS mēnešu izmēģinājumu/pagaidu faili | Nē |
| `data/climate-demo.sqlite`, `data/climate.sqlite`, `data/legacy-demo.sqlite` | Agrīnie demonstrācijas/izstrādes SQLite faili | **Nē; pašreizējā vietne tos nelasa** |
| `public/countries.geojson` | Iesaldētas 195 valstu robežas kartei un ETL svaru aprēķinam | Jā, ģeometrijas avots |
| `public/territories.geojson` | 47 citas teritorijas neinteraktīvam kartes slānim | Jā, tikai kartes attēlošanai |
| `src/countryCatalog.json`, `public/flags/` | Valstu latviskie nosaukumi un karogi | Jā, saskarnei |
| `public/data/`, `dist/` | Ikdienas uzdevuma ģenerēts statiskais eksports un GitHub Pages būvējums | Nē; var ģenerēt atkārtoti |

Docker volume fiziski atrodas Docker Desktop Linux vidē kā `/var/lib/docker/volumes/project_europe_climate_pgdata/_data`, nevis projekta `data/` mapē. Windows failu pārlūkā to nevajag rediģēt tieši. `docker compose down` saglabā volume; `docker compose down -v` **dzēš** datubāzes volume un nav jālieto, ja jāglabā dati.

## Koda izvietojums

| Ceļš projektā | Atbildība |
| --- | --- |
| `src/App.tsx`, `src/PeriodPicker.tsx` | Lapas izkārtojums, periods, valsts profils, CSV eksports |
| `src/ClimateMap.tsx`, `src/styles.css` | MapLibre karte, krāsu/teritoriju slāņi un vizuālais stils |
| `src/dataClient.ts`, `src/types.ts` | API vai statisko JSON datu ielāde un perioda aprēķins |
| `backend/app.py` | FastAPI metadatu, anomāliju un laika rindas galapunkti |
| `backend/db.py`, `compose.yaml` | Datubāzes shēma un PostGIS konteiners |
| `backend/etl/` | ARCO/CDS iegūšana, režģa svari, valstu dienu un normu aprēķins |
| `backend/export_static.py` | Datu momentuzņēmuma eksports statiskai vietnei |
| `scripts/start_local_site.ps1` | Lokālās reālo datu vietnes palaišana |
| `scripts/run_daily_update.ps1`, `scripts/install_daily_task.ps1`, `scripts/daily_update_status.ps1` | Ikdienas automatizācija un pārbaude |
| `scripts/arco_*.ps1`, `scripts/start_arco_*.ps1` | Importa palaišana un stāvokļa pārbaude |
| `tests/` | Valstu kataloga, salu, svaru un garā gada pārbaudes |

## Tabulas un pašreizējais tvērums

| Tabula | Atslēga | Saturs | Rindas 2026-11-09 |
| --- | --- | --- | ---: |
| `countries` | `iso3` | 195 valstu katalogs, kvalitātes klase, pārklājums, robežu ģeometrija | 195 |
| `baseline_daily` | `(iso3, day)` | Katras dienas valstu vidējā 1991-01-01–2020-12-31 | 2 060 104 |
| `daily` | `(iso3, day)` | Vietnē skatāmās valstu dienas 2020-01-01–2026-11-03 | 469 812 |
| `normals` | `(iso3, mmdd)` | 1991–2020 kalendāra dienu normas; 29. februāris no garajiem gadiem | 68 808 |
| `ingested_months` | `month` | Pabeigto mēnešu kontrolpunkti | atkarīgs no importa |
| `dataset_info` | `id` | Datu izcelsmes režīms (`era5_land`) | 1 |

Vēsture un attēlojamie dati aptver 188 valstis, katru dienu bez iztrūkumiem attiecīgajā intervālā. 2020. gads apzināti ir abās dienu tabulās. Kvalitātes sadalījums: `grid` 174, `limited` 12, `proxy` 2 (Monako un Vatikāns), `unavailable` 7. Šīm septiņām salu valstīm skaitļi netiek ģenerēti: Kiribati, Maldīvija, Māršala Salas, Nauru, Seišelas, Tonga, Tuvalu. Tās paliek 195 valstu katalogā un kartē ar neitrālu krāsu.

Datubāzes kopējais izmērs šajā datumā ir ap 276 MB. Pirmais ikdienas cikls papildināja datus līdz 2026-11-03; turpmāk `GlobalClimateDailyUpdate` katru rītu pārbauda ARCO pieejamās pilnās UTC dienas. Vēsturiskais ARCO imports pabeidzās 2026-10-30; `GlobalClimateARCOResume` ir tikai šī vēsturiskā darba atsākšanai pēc pieteikšanās un neaizstāj ikdienas uzdevumu. Vecais `GlobalClimateERA5Resume` ir atspējots. Skatīt [AUTOMATION.md](AUTOMATION.md).

## Datu ceļš

1. Vēsturisko posmu veidoja `backend/etl/arco_2026.py` un `backend/etl/arco_backfill.py`; jaunas dienas tagad pievieno `backend/etl/arco_daily_update.py`. Visi lasa oficiālo ERA5-Land ARCO Zarr 2 m temperatūru. Dienas vērtība ir 24 UTC stundu vidējais.
2. `backend/etl/ingest.py` sagatavo valstu sauszemes režģa šūnu platību svarus no `public/countries.geojson` un derīgajiem ERA5-Land punktiem. Svari tiek kešoti `data/weights-*.npz`.
3. Vienas dienas transakcija ieraksta valstu rezultātus PostGIS. Pilni globālie režģu faili netiek glabāti ilgtermiņā.
4. `normals` aprēķina no saglabātās `baseline_daily` vēstures. `backend/app.py` API perioda pieprasījumā izmanto tikai PostGIS `daily` un `normals`, bez ARCO lejupielādes.
5. `src/dataClient.ts` pieprasa API; `src/ClimateMap.tsx` pārkrāso MapLibre karti, un `src/App.tsx` rāda valsts profilu.

Skatīt [ARCHITECTURE.md](ARCHITECTURE.md) metodikai, kvalitātes noteikumiem un sezonu aprēķinam. ERA5-Land ir reanalīze, nevis staciju mērījumi; `proxy` un `limited` vērtības jāinterpretē ar norādīto nenoteiktību.

## Palaišana un pārbaude

PowerShell projekta mapē:

```powershell
.\scripts\start_local_site.ps1
.\scripts\arco_backfill_status.ps1
```

Pirmais skripts palaiž/pārbauda PostGIS, FastAPI portā `8013` un Vite portā `5173`, pieprasa datubāzes `era5_land` režīmu un izvada saites. Atveriet `http://127.0.0.1:5173/`. `.env` satur lokālo PostGIS paroli; `scripts/postgis-env.ps1` to ielasa `DATABASE_URL`. `.env` un `data/` ir ignorēti avota kontrolē.

Īsie vaicājumi:

```powershell
docker compose exec -T db psql -U climate -d climate -c "SELECT mode FROM dataset_info WHERE id=1;"
docker compose exec -T db psql -U climate -d climate -c "SELECT MIN(day), MAX(day), COUNT(*) FROM daily;"
Invoke-RestMethod http://127.0.0.1:8013/api/meta
```

## Rezerves kopija

Docker volume nav rezerves kopija. Pirms Docker dzēšanas vai pārvietošanas izveidojiet `pg_dump` failu, piemēram:

```powershell
New-Item -ItemType Directory -Force data\backups | Out-Null
docker compose exec -T db pg_dump -U climate -d climate -Fc -f /tmp/climate.dump
docker cp project_europe-db-1:/tmp/climate.dump data\backups\climate.dump
```

Pārbaudiet, ka `data\backups\climate.dump` pastāv un nav tukšs. Glabājiet vēl vienu kopiju ārpus šī datora. Atjaunošanai vispirms izveidojiet tukšu `climate` datubāzi atsevišķā PostGIS instancē, tad lietojiet `pg_restore`; neveiciet atjaunošanu virs darba datubāzes bez atsevišķas rezerves kopijas.

## Statiskā vietne

`backend/export_static.py` var izveidot `public/data/meta.json`, `countries.json`, `normals.json` un vienu JSON failu katram mēnesim. Ar `VITE_STATIC_DATA=1` pārlūks perioda vidējo aprēķina no šiem failiem, tāpēc GitHub Pages izvietošanai nav vajadzīgs dzīvs FastAPI/PostGIS. Tas ir eksporta momentuzņēmums: jaunas dienas parādās tikai pēc nākamā importa, eksporta un izvietošanas. Lokālā vietne pašlaik izmanto dzīvu API, nevis šo statisko režīmu.
