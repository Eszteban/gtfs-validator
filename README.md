# GTFS Validator Microservice

Python-alapú aszinkron GTFS validátor mikroszerviz (SZTE Felhő DevOps 2026 projekt).

A szolgáltatás célja feltöltött GTFS zip fájlok relációs integritásának és szintaxisának ellenőrzése, majd aszinkron riport generálása.

---

## Architektúra és Biztonsági Koncepció
- **Python**: 3.12 (hivatalos `python:3.12-slim` alapimage)
- **Multi-stage Docker build**:
  - `builder`: Virtuális környezet és függőségek fordítása/telepítése.
  - `runner`: Minimális runtime környezet (pip cache és build eszközök nélkül a legkisebb sebezhetőségi felület / Trivy scan érdekében).
- **Non-root futtató felhasználó**: `appuser` (`UID: 10001`, `GID: 10001`).
- **Beépített HEALTHCHECK**: Python standard könyvtárral (független a külső curl csomagtól, minimális CVE-kockázat).
- **Adatperzisztencia**: Docker named volume-ok a feltöltésekhez és az SQLite adatbázishoz.
- **Megfigyelhetőség (Observability)**: Prometheus metrikák (`/metrics`), standard HTTP és egyedi alkalmazásszintű mérőszámok.
- **Keretrendszer**: FastAPI, SQLAlchemy 2.0, Pydantic v2.

---

## Megfigyelhetőség, Metrikák és SLI/SLO (7 pont)

A mikroszerviz beépített Prometheus instrumentációval rendelkezik (`prometheus-fastapi-instrumentator`), amely a `/metrics` végponton nyíltan exportálja a standard HTTP és az egyedi GTFS üzleti metrikákat.

### 1. Egyedi Prometheus Alkalmazásmetrikák (`app/metrics.py`)
- **`gtfs_validation_jobs_total{status="..."}`**: Összes befejezett validációs feladat számlálója a végállapot (`COMPLETED`, `FAILED`) szerint.
- **`gtfs_validation_duration_seconds{status="..."}`**: A validációs feldolgozás futási idejének hisztogramja másodpercben (finomhangolt vödrökkel: `0.01`, `0.05`, `0.1`, `0.5`, `1.0`, `2.5`, `5.0`, `10.0`).
- **`gtfs_validation_errors_total{error_type="..."}`**: Feltárt szintaktikai és relációs integritási hibák számlálója hibakódonként címkézve (pl. `FOREIGN_KEY_VIOLATION`, `MISSING_REQUIRED_COLUMN`, `INVALID_COORDINATE`).

### 2. SLI / SLO Definíciók (Google SRE alapelvek szerint)

#### SLI/SLO 1: API Rendelkezésre állás (Availability)
- **Service Level Indicator (SLI)**:
  A sikeres (nem 5xx státuszú) HTTP kérések aránya az összes beérkező HTTP kéréshez képest:
  $$\text{SLI}_{\text{availability}} = \frac{\sum \text{rate}(http\_requests\_total\{status!=\sim"5.."\} [5m])}{\sum \text{rate}(http\_requests\_total[5m])}$$
- **Service Level Objective (SLO)**:
  A beérkező kérések legalább **99.5%**-a sikeres (nem 5xx szerveroldali hiba) 30 napos gördülő időablakban mérve.

#### SLI/SLO 2: Validációs háttérfeldolgozás hatékonysága és késleltetése (Processing Latency & Success)
- **Service Level Indicator (SLI)**:
  A sikeresen befejeződött és 5 másodpercen belül lefutott GTFS validációk aránya az összes elindított validációs feladathoz viszonyítva:
  $$\text{SLI}_{\text{latency}} = \frac{\sum \text{rate}(gtfs\_validation\_duration\_seconds\_bucket\{le="5.0", status="COMPLETED"\}[5m])}{\sum \text{rate}(gtfs\_validation\_jobs\_total[5m])}$$
- **Service Level Objective (SLO)**:
  A validációs feladatok legalább **95.0%**-a sikeresen és 5.0 másodpercnél rövidebb idő alatt fut le.

### 3. Prometheus felület elérése és konfigurációja
A `docker-compose.yml` tartalmazza a Prometheus (`prom/prometheus:v2.54.1`) konténert, amely 5 másodpercenként (`scrape_interval: 5s`) gyűjti a metrikákat a `gtfs-validator:8000/metrics` címről.
- **Prometheus Web UI**: `http://localhost:9090`
- **Célpontok állapota (Targets)**: `http://localhost:9090/targets`

### 4. Ajánlott PromQL lekérdezések ellenőrzéshez

```promql
# 1. Feldolgozott GTFS feladatok száma státuszonként:
sum by (status) (gtfs_validation_jobs_total)

# 2. GTFS validációs hibák eloszlása hibakódok szerint:
sum by (error_type) (gtfs_validation_errors_total)

# 3. 95. percentilis feldolgozási idő (P95 latency):
histogram_quantile(0.95, sum by (le) (rate(gtfs_validation_duration_seconds_bucket[5m])))

# 4. Kérések másodpercenkénti rátája (RPS) végpontonként:
sum by (handler, status) (rate(http_requests_total[1m]))

# 5. API hibaarány (5xx válaszok aránya):
sum(rate(http_requests_total{status=~"5.."}[5m])) / sum(rate(http_requests_total[5m]))
```

---

## CI/CD Folyamat és Minőségi Kapuk (Quality Gates)

A projekt egy teljesen automatizált GitHub Actions pipeline-t (`.github/workflows/ci.yml`) alkalmaz, amely a tantárgyi rubrika alábbi követelményeit fedi le:

### 1. Kapu: Titokszivárgás-védelem (`secret-scan` job)
- **Eszköz**: TruffleHog OSS.
- **Funkció**: Minden commit és PR esetén átvizsgálja a repository történetét véletlenül kikerült API-kulcsok, tokenek vagy jelszavak után (titokkezelési megfelelőség).

### 2. Kapu: Kódminőség és Automatikus Tesztelés (`lint-and-test` job - 9 pont)
- **Gyorsítótárazás**: Python `pip` cache a minimális futási idő eléréséhez.
- **Statikus analízis**: `ruff check .` linter ellenőrzi a kódot (kivéve a FastAPI-specifikus dependenciákat és lágy formázási szabályokat).
- **Automatizált egység- és integrációs tesztek**: `pytest -v --junitxml=test-results.xml`.
- **Artifactkezelés**: A teszteredményeket tartalmazó JUnit XML riport automatikusan feltöltésre kerül GitHub Actions artifactként (`test-results-junit`).

### 3. Kapu: Konténer Biztonság, Sérülékenység-vizsgálat és SBOM (`container-security-and-sbom` job - 7 pont)
- **Buildx & Docker Cache**: A konténerkép a GitHub Actions beépített réteg-gyorsítótárával (`cache-from/to: type=gha`) épül fel.
- **Sérülékenység-vizsgálat (Vulnerability Scanning)**: Az Aqua Security Trivy action átvizsgálja a konténerkép operációs rendszerét és Python könyvtárait `CRITICAL` és `HIGH` szintű sebezhetőségek után, majd SARIF formátumú riportot generál.
- **SBOM (Software Bill of Materials) generálás**: Az Anchore Syft eszköz segítségével automatikusan előáll mind **SPDX-JSON**, mind **CycloneDX-JSON** formátumú szoftverleltár.
- **Artifactkezelés**: Az SBOM leltárak és a Trivy vizsgálati jelentések letölthető GitHub Actions artifactként mentődnek (`security-and-sbom-artifacts`).

---

## Konténeres futtatás Docker Compose-zal

### 1. Környezeti változók előkészítése
```bash
cp .env.example .env
```

### 2. Alkalmazás és Prometheus indítása a háttérben
```bash
docker compose up --build -d
```

### 3. Konténer státusz és Healthcheck ellenőrzése
```bash
docker compose ps
```
A kimenetben mindkét szolgáltatás (`gtfs-validator` és `prometheus`) futó állapotban látható.

### 4. Naplók megtekintése
```bash
docker compose logs -f gtfs-validator
```

### 5. Non-root felhasználó (UID 10001) ellenőrzése a futó konténerben
```bash
docker compose exec gtfs-validator id
```
Elvárt kimenet:
```text
uid=10001(appuser) gid=10001(appuser) groups=10001(appuser)
```

### 6. Végpontok manuális tesztelése
```bash
# Egészségügyi ellenőrzés:
curl -i http://localhost:8000/health

# Prometheus metrikák ellenőrzése:
curl -i http://localhost:8000/metrics
```

### 7. Leállítás és takarítás
```bash
# Konténerek leállítása:
docker compose down

# Konténerek és volume-ok törlése:
docker compose down -v
```

---

## Lokális fejlesztői futtatás (Docker nélkül)

### 1. Függőségek telepítése
```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1   # Linuxon: source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Alkalmazás indítása
```bash
uvicorn app.main:app --reload
```

### 3. Tesztek és linter futtatása
```bash
ruff check .
pytest -v
```

---

## API Végpontok

- **`GET /health`**
  - Visszatérési érték: `{"status": "healthy"}` (200 OK)
- **`GET /metrics`**
  - Nyílt Prometheus formátumú metrikák (HTTP kérések, késleltetések, GTFS validációs mutatók)
- **`POST /api/v1/jobs`**
  - GTFS `.zip` fájl feltöltése (`multipart/form-data`)
  - Válasz: `JobCreateResponse` (201 Created), a háttérben elindul az ellenőrzés
- **`GET /api/v1/jobs/{job_id}`**
  - Lekérdezi a feladat állapotát (`QUEUED`, `PROCESSING`, `COMPLETED`, `FAILED`)
- **`GET /api/v1/jobs/{job_id}/report`**
  - Részletes validációs jelentés (relációs hibák, hiányzó oszlopok, rekord statisztikák)
