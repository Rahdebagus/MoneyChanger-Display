# PAM Rate Board & Remote Display

Internal system for PT. Pradnyana Artha Mandiri: read exchange rates off a photo
with OCR, correct them, generate the branded PAM rate board, and push it to TVs
in the branches.

The board image itself is produced by the original Pillow generator and is
unchanged — a regression test compares every build against a checked-in
baseline PNG byte for byte.

---

## What it does

| | |
| --- | --- |
| **Generator** | Upload image → OCR → edit rates → **Generate & Save** → download PNG |
| **Versions** | Every generate saves an immutable version. Editing a live board creates a new version; it never overwrites what is on screen. |
| **Displays** | A TV opens `/display`, shows a pairing code, an admin approves it, and the TV gets its own revocable credential. |
| **Publishing** | Publish a *ready* version to one display, several, or a whole branch — now or on a schedule. Rollback and refresh are one click. |
| **Offline** | A paired TV keeps showing its last board through a network outage and a reload. |

---

## Requirements

- **Python 3.10** (3.10.11 verified)
- **Node.js 20+** (22.22.2 verified)
- **MySQL 8 or MariaDB 10.4+** — the local XAMPP service is MariaDB 10.4.32 and works

---

## Setup (Windows PowerShell)

### 1. Python environment

One environment for the whole repository, at the root:

```powershell
cd C:\xampp\htdocs\Project\sukunan-money-chager
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
```

> **Do not upgrade PaddlePaddle.** `paddlepaddle 3.3.1` with `paddleocr 2.7.3`
> fails at inference with `OneDnnContext does not have the input Filter
> ... [operator < fused_conv2d >]`. `requirements.txt` pins the combination that
> was verified working by an actual OCR run: **paddleocr 2.7.3 + paddlepaddle 2.6.2**.

### 2. Database

Start MySQL/MariaDB (in XAMPP: **Start** next to MySQL), then:

```powershell
C:\xampp\mysql\bin\mysql.exe -u root -e "CREATE DATABASE pam_rate_board CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
```

### 3. Configuration

```powershell
Copy-Item .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(48))"   # paste into SECRET_KEY
```

Edit `.env` and set `DATABASE_URL` and `SECRET_KEY`.

### 4. Migrations

```powershell
cd backend
alembic upgrade head
```

### 5. First admin account

No password is baked into the source and there is no public registration:

```powershell
cd backend
python -m app.cli create-admin
```

It prompts for the username and password. For an unattended install, set
`PAM_ADMIN_PASSWORD` in the environment first.

Optionally create branches:

```powershell
python -m app.cli create-branch --name "Kuta"
```

Check everything is wired up:

```powershell
python -m app.cli check
```

---

## Running

API and frontend are sufficient for saving PNG and immediate publication. Activate `.venv` for Python commands. The optional maintenance process handles disk cleanup after history deletion and scheduled publication.

```powershell
# 1. API  (from backend\)
cd backend
uvicorn app.main:app --reload --port 8000

# Optional maintenance — cleans deleted media and fires scheduled publishes  (from backend\)
cd backend
python -m app.workers.runner

# 3. Frontend  (from frontend\)
cd frontend
npm install
npm run dev
```

| | |
| --- | --- |
| Admin UI | http://localhost:5173 |
| TV player | http://localhost:5173/display |
| API docs | http://localhost:8000/docs |

> The entry point is `app.main:app`. Save commits the rates, renders PNG with Pillow in the same request, then returns `ready`. No PNG queue or Cron worker is required.
> For shared cPanel hosting, follow [the direct-PNG release guide](docs/direct-png-deployment.md), including the additive migration and local frontend build.

### Pointing the frontend at another host

The frontend defaults to the hostname it was loaded from, on port 8000, so a TV
or phone on the same LAN works with no rebuild. To override:

```powershell
cd frontend
Copy-Item .env.example .env.local    # then edit VITE_API_BASE_URL
```

---

## Pairing a TV

1. Open `http://<server>:5173/display` on the TV. A six-character code appears.
2. In the admin UI go to **Display → Pasangkan Display Baru**, enter the code,
   name the display and pick its branch.
3. The TV claims its own credential within a few seconds and switches to the
   waiting screen. No admin account is ever entered on the TV.
4. Generate a rate board, then use **Tampilkan ke Display**.

Use the browser's kiosk/fullscreen mode for an unattended install — a web page
cannot put itself into fullscreen without a user gesture, so the **Layar Penuh**
button is offered instead of a promise the browser would refuse.

---

## Tests

```powershell
# Backend — runs against a real MySQL/MariaDB database, not SQLite,
# because the behaviour under test depends on SQL semantics.
C:\xampp\mysql\bin\mysql.exe -u root -e "CREATE DATABASE IF NOT EXISTS pam_rate_board_test CHARACTER SET utf8mb4;"
cd backend
pytest

# Frontend
cd frontend
npm run lint
npm test
npm run build
```

---

## Documentation

| Document | Contents |
| --- | --- |
| [frontend/docs/optimasi.md](frontend/docs/optimasi.md) | History deletion, display synchronization and resource use |
| [docs/architecture.md](docs/architecture.md) | How it fits together, data model, the publishing protocol |
| [docs/deployment.md](docs/deployment.md) | Production deployment, backup/restore, troubleshooting |
| [docs/cleanup-report.md](docs/cleanup-report.md) | What was removed in the 2.0 restructure and why |
| [docs/implementation-status.md](docs/implementation-status.md) | Build log, measurements, known limitations |

---

## Project layout

```
backend/
  app/
    main.py            FastAPI app factory  (uvicorn app.main:app)
    cli.py             create-admin, create-branch, check
    core/              config, security, logging, rate limiting
    db/                engine and session
    models/            SQLAlchemy models
    schemas/           request/response validation
    api/routes/        auth, versions, publications, displays, device, media, ws
    services/          generator, ocr, parser, mapper, publishing, pairing, jobs
    workers/runner.py  media cleanup + publication scheduler
  assets/              pam_bg.png, pam_logo.png  (used by the board generator)
  migrations/          Alembic
  tests/               regression + integration tests
frontend/
  src/
    features/          generator, auth, dashboard, history, displays, player, ...
    components/        shared UI
    services/          apiClient.js  (every network call)
    hooks/  context/   shared state
storage/               generated media, flag cache  (gitignored, durable volume)
docs/                  architecture, deployment, cleanup, status
scripts/               maintenance helpers
```
