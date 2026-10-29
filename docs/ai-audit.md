# AI-Támogatott Munkafolyamat Szakmai Ellenőrzése és Audit Napló

Ez a dokumentum a GTFS Validátor DevOps projekt fejlesztése során alkalmazott mesterséges intelligencia (AI) eszközök használatát, a szakmai kontrollt, valamint az elfogadott és felülbírált mérnöki döntéseket mutatja be a tantárgyi rubrika **"Az AI-támogatott munkafolyamat szakmai ellenőrzése (4 pont)"** követelményeinek megfelelően.

---

## 1. Alkalmazott AI-eszközök és Szerepkörük

- **Alkalmazott technológia**: Antigravity AI pair programming asszisztens (Google DeepMind Advanced Agentic Coding, Gemini modellek).
- **Szerepkör és határok**:
  - Az AI-t technológiai akcelerátorként, "társprogramozóként" használtuk: boilerplate kódok gyors előállítására, Helm sablonok szintaktikai vázlatára, Docker multi-stage minták generálására és PromQL lekérdezések szintaxisának ellenőrzésére.
  - Az architektúrális döntések, a biztonsági szabályok érvényesítése, a hibák felülvizsgálata és a kódminőség ellenőrzése **kizárólag emberi mérnöki felelősségi körben** maradt.

---

## 2. Elfogadott Mérnöki Döntések és Szakmai Indoklásuk

Az alábbi AI által javasolt megoldásokat szakmai felülvizsgálat után elfogadtuk, mivel azok bizonyíthatóan növelték a rendszer biztonságát, teljesítményét és robusztusságát:

### A) Nem emelt szintű futtató felhasználó (`UID: 10001`, `appuser`)
- **Javaslat**: A konténer ne root felhasználóként fusson, hanem hozzunk létre egy dedikált rendszercsoportot és usert (`10001:10001`).
- **Szakmai indoklás**: A rootless konténerfuttatás a felhőnatív biztonság egyik legfontosabb alappillére. Kivédi a konténer-kitörési (container breakout) sebezhetőségeket, és teljesíti a Kubernetes Pod Security Standards legszigorúbb (Restricted) profilját.

### B) Beépített Python `urllib` a konténeres `HEALTHCHECK`-ben a `curl` helyett
- **Javaslat**: A Dockerfile `HEALTHCHECK` direktívájához ne telepítsük a `curl` csomagot az `apt-get`-tel a `python:3.12-slim` image-be, hanem futtassunk egy egyszerű beépített Python parancsot.
- **Szakmai indoklás**: A `curl` és annak tranzitív könyvtárai (libcurl, openssl csomagok) felesleges rétegeket képeznek, és folyamatos biztonsági frissítéseket, CVE-kockázatokat hoznának be. A Python standard könyvtárának használatával az image minimális méretű maradt, és a Trivy biztonsági vizsgálat 0 sebezhetőséget talált.

### C) Multi-stage Docker Build (Builder és Runner rétegek elválasztása)
- **Javaslat**: Kétfázisú build folyamat alkalmazása: egy `builder` fázis a virtuális környezet és függőségek fordítására, valamint egy karcsúsított `runner` fázis a futtatásra.
- **Szakmai indoklás**: Megakadályozza, hogy a fordítóeszközök, build-időbeli scriptek és a pip gyorsítótár bekerüljön a végleges futtató konténerbe, radikálisan csökkentve az image méretét és a támadási felületet.

### D) Pydantic v2 és SQLAlchemy 2.0 típusbiztos adatmodell
- **Javaslat**: Pydantic v2 `ConfigDict(from_attributes=True)` használata az adatbázis-modellek és a REST API válaszok közötti konverzióra.
- **Szakmai indoklás**: Típusbiztos API szerződést garantál, automatikus validációt ad, miközben az adatbázis-réteg teljesen felcserélhető marad SQLite (fejlesztés) és PostgreSQL (éles üzem) között.

---

## 3. Felülbírált, Elutasított és Manuálisan Javított AI Javaslatok

Az AI által javasolt minták közül több kritikus ponton is hibás vagy szuboptimális megoldást kínált, amelyeket a mérnöki felülvizsgálat során elvetettünk vagy manuálisan javítottunk:

### A) GitHub Actions Trivy Action Verzióhiba és SARIF Integráció (Kritikus javítás)
- **A hiba**: Az AI kezdetben az elavult `@master` vagy nem kompatibilis lebegő címkét (`@0.24.0`) javasolta a `.github/workflows/ci.yml`-ben a sérülékenység-vizsgálathoz, amely a modern GitHub Actions Ubuntu runner környezetben figyelmeztetést vagy végzetes futási hibát eredményezett.
- **Mérnöki beavatkozás**: 
  - Manuálisan felülbíráltuk és a stabil, tesztelt `aquasecurity/trivy-action@0.28.0` verziót rögzítettük.
  - Két lépésre bontottuk a szkennelést: egy terminálban olvasható táblázatos összefoglalóra, valamint egy szabványos SARIF riportra (`trivy-results.sarif`), amely bekerült a CI letölthető biztonsági artifactjai közé.

### B) Külső GTFS könyvtárak (pl. `partridge`, `gtfs-kit`, Pandas) elutasítása
- **A hiba**: Az AI korai javaslatai kész külső Python GTFS csomagok (és ezáltal a masszív méretű Pandas és NumPy) telepítését ajánlották a fájlok olvasásához.
- **Mérnöki beavatkozás**: 
  - Határozottan elutasítottuk a felesleges függőségeket.
  - Helyette a Python beépített `zipfile` és `csv` moduljaira épülő, könnyűsúlyú, relációs integritás-ellenőrzőt készítettünk (`app/validator.py`).
  - **Eredmény**: Az alkalmazás indítási ideje ezredmásodperces nagyságrendűvé vált, a memóriahasználat minimális maradt, és elkerültük a külső adatfeldolgozó könyvtárak sebezhetőségi kitettségeit.

### C) SQLite szálkezelési hiba és BackgroundTasks izoláció a tesztekben
- **A hiba**: Az AI az egységtesztekhez egyszerű memóriabeli SQLite adatbázist (`sqlite:///:memory:`) generált. Azonban az aszinkron háttérfolyamat (`BackgroundTasks`) a FastAPI-ban külön szálon fut, ami SQLite memóriabázisnál egy vadonatúj, üres adatbázishoz csatlakozott, azonnali `OperationalError: no such table: validation_jobs` hibát dobva.
- **Mérnöki beavatkozás**:
  - Felismertük a konkurens adatbázis-hozzáférés hibáját.
  - A tesztkörnyezetet átalakítottuk: a `pytest` `tmp_path` fixture-jének segítségével izolált, ideiglenes fájlalapú SQLite adatbázist és monkeypatchingelt session factory-t vezettünk be.
  - Ez garantálta, hogy mind az API végpont, mind a háttérmunkás ugyanazt az izolált adatbázist lássa, és a tesztek 100%-ban megbízhatóvá váljanak.

---

## 4. Végső Mérnöki Felelősségvállalási Nyilatkozat

> **"A mérnök felel a diff-ért."**

Kijelentjük, hogy a GTFS Validátor mikroszerviz teljes forráskódját, konténerizációs receptjét, CI/CD pipeline-ját, Kubernetes manifesztjeit és IaC konfigurációját sorról sorra átvizsgáltuk, megértettük és teszteltük. 
Az AI csupán produktivitásnövelő asszisztensként szolgált; a végső technológiai döntésekért, a hibák elhárításáért és a működési bizonyítékok valódiságáért a projektet készítő mérnök vállal teljes szakmai felelősséget.

