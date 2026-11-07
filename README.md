# Grainit til Home Assistant (v0.2)

Custom integration, der henter registrerede læs (flytning af gylle og biomasse) fra Grainit-portalen og viser dem i Home Assistant: i dag, denne uge, denne måned og dette gødningsår, det seneste læs, de seneste 20 læs og hele historikken i grafer.

Grainit har ikke noget offentligt API. Integrationen logger ind på samme måde som hjemmesiden og læser de samme data som siden "Bevægelser/log".

## Installation

### Via HACS

1. HACS → ⋮ → *Custom repositories* → tilføj `https://github.com/Cytram/GrainIt` som type *Integration*.
2. Installér "Grainit", og genstart Home Assistant.
3. Indstillinger → Enheder og tjenester → Tilføj integration → "Grainit", og indtast din Grainit-e-mail og adgangskode.

### Manuelt

1. Kopiér `custom_components/grainit` til `<HA config>/custom_components/grainit` (erstat den gamle version, hvis du har en).
2. Genstart Home Assistant.
3. Indstillinger → Enheder og tjenester → Tilføj integration → "Grainit", og indtast din Grainit-e-mail og adgangskode.

Valgfrit: Sæt dashboardet i `dashboard/grainit_dashboard.yaml` og notifikationen i `dashboard/grainit_notifikation.yaml` op (vejledningen står øverst i hver fil).

Opgradering fra v0.1: Slet først den gamle Grainit-opsætning under Enheder og tjenester, genstart, og tilføj den igen. De gamle "24 timer"-sensorer forsvinder.

## Sensorer

Pr. produkt og retning, fx `raagylle_kvaeg_ud`, `afgasset_gylle_ind`, `dybstroeelse_ud`:

| Entitet | Betydning |
|---|---|
| `sensor.grainit_<nøgle>_i_dag` | tons i dag |
| `sensor.grainit_<nøgle>_denne_uge` | tons denne uge (mandag–søndag) |
| `sensor.grainit_<nøgle>_denne_maaned` | tons denne måned |
| `sensor.grainit_<nøgle>_goedningsaar` | tons siden 1. august |
| `sensor.grainit_<nøgle>_laes_i_dag` | antal læs i dag |
| `sensor.grainit_<nøgle>_seneste` | tidspunkt for seneste læs |

Samlet:

| Entitet | Betydning |
|---|---|
| `sensor.grainit_seneste_laes` | tidspunkt for seneste læs. Attributter: produkt, tons, fra, til, chauffør og `laes` = de seneste 20 læs |
| `sensor.grainit_laes_i_dag` | antal læs i dag |
| `sensor.grainit_laes_denne_maaned` | antal læs denne måned |

Nye produkter dukker automatisk op.

## Grafer med hele historikken

Ved opstart og hver 6. time importeres hele historikken til Home Assistants langtidsstatistik som `grainit:<nøgle>` (akkumulerede tons pr. time). Et statistics-graph-kort med `stat_types: [change]` og `period: day/week/month` viser så tons pr. periode, også alt fra før integrationen blev installeret.

## Event ved nye læs

Hvert nyt læs udløser eventet `grainit_new_load` med `product`, `direction`, `tonnes`, `kg`, `driver`, `from`, `to`, `time` og `registration_id`. Det kan bruges til notifikationer (se `grainit_notifikation.yaml`).

## Sådan taler den med Grainit

- Login: `POST https://portal.grainit.net/?action=login_sql` (formularfelter: `offset`, `email`, `password`, `remember_login`). Sessionen gemmes i sin egen cookie jar.
- Læs: `GET https://portal.grainit.net/ajax/dashboard_status.php?action=get_movements_status_details_v2&start_date=DD-MM-YYYY&end_date=DD-MM-YYYY&…` returnerer `{"success":1,"html":"<table>…"}` med én række pr. læs.
- Portalen blander UTF-8 og Latin-1 i sine svar, så teksten læses som UTF-8 med cp1252 som reserve.
- Hvis portalen svarer "Ingen adgang" eller noget, der ikke er JSON, logger den ind igen og prøver én gang til. Fejler det stadig, beholder sensorerne deres seneste værdier til næste opdatering.
- Opdateringsinterval: 15 minutter som standard, kan ændres under integrationens indstillinger.

## Filer

- `api.py` – login, hentning og parsing af tabellen med læs
- `summary.py` – totaler pr. dag/uge/måned/gødningsår (ingen afhængigheder af HA)
- `statistics.py` – import til langtidsstatistik
- `__init__.py` – opsætning, coordinator, events
- `sensor.py` – sensorerne
- `config_flow.py` – opsætning, nyt login (reauth) og indstillinger

## Test

```bash
python3 tests/test_grainit.py
```

Kører uden at Home Assistant eller aiohttp er installeret.
