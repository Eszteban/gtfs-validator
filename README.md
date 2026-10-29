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
- **Keretrendszer**: FastAPI, SQLAlchemy 2.0, Pydantic v2.

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

### 2. Alkalmazás indítása és buildelése a háttérben
```bash
docker compose up --build -d
```

### 3. Konténer státusz és Healthcheck ellenőrzése
```bash
docker compose ps
```
A kimenetben látható lesz a konténer állapota: `Up (healthy)`.

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

### 6. Healthcheck végpont manuális tesztelése
```bash
curl -i http://localhost:8000/health
```
Válasz: `HTTP/1.1 200 OK` és `{"status": "healthy"}`.

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
- **`POST /api/v1/jobs`**
  - GTFS `.zip` fájl feltöltése (`multipart/form-data`)
  - Válasz: `JobCreateResponse` (201 Created), a háttérben elindul az ellenőrzés
- **`GET /api/v1/jobs/{job_id}`**
  - Lekérdezi a feladat állapotát (`QUEUED`, `PROCESSING`, `COMPLETED`, `FAILED`)
- **`GET /api/v1/jobs/{job_id}/report`**
  - Részletes validációs jelentés (relációs hibák, hiányzó oszlopok, rekord statisztikák)
