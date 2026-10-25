# Deployment & operations

For the installed cPanel/Passenger application, use [direct PNG deployment](direct-png-deployment.md). The Docker/standalone examples below are alternatives, not commands to overwrite an existing Passenger installation.

## Before anything else

- `SECRET_KEY` must be set. In production the app refuses to start without it.
  Rotating it logs everyone out, which is the intended behaviour.
- `ENVIRONMENT=production` disables `/docs` and enforces the checks above.
- Run the API **without** `--reload`.
- Serve the frontend as a **build** (`npm run build`), never the dev server.
- Put HTTPS/WSS at the reverse proxy. A TV on a hostile network is still a
  device on your network.
- `CORS_ORIGINS` must list specific origins. Never `*`.
- Keep the database on a private network. Do not publish port 3306.

---

## Docker Compose

```bash
cp .env.example .env     # set SECRET_KEY, DB_PASSWORD, DB_ROOT_PASSWORD,
                         #     PUBLIC_BASE_URL, CORS_ORIGINS
docker compose up -d --build
docker compose exec api alembic upgrade head
docker compose exec api python -m app.cli create-admin
```

| Service | Role |
| --- | --- |
| `db` | MySQL 8, UTC, `STRICT_TRANS_TABLES`, private network only |
| `api` | FastAPI on :8000 |
| `worker` | optional media cleanup + publication scheduler; no PNG generation |
| `frontend` | nginx serving the built SPA on :8080 |

Volumes: `db_data`, `media_data` (generated boards — back this up), and
`paddle_models` so the OCR models are downloaded once rather than on every
container start.

The host's `.venv` and `node_modules` never enter the image; `.dockerignore`
excludes them.

### Scaling

`worker` is safe to scale: job claims and schedule claims are both atomic, so
nothing runs twice.

`api` can also be scaled, with one caveat — websocket fan-out goes through the
`event_outbox` table, which each API process tails independently. That works
across processes, but each adds a poll every `EVENT_POLL_INTERVAL_SECONDS`.
With more than a handful of API processes, move fan-out to a real pub/sub.

---

## Manual deployment

```powershell
# API
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2

# Worker (separate service/terminal)
cd backend
python -m app.workers.runner

# Frontend
cd frontend
npm ci
npm run build          # serve dist/ with nginx, IIS or Apache
```

The SPA needs a **fallback to `index.html`** for unknown paths, or a TV
reloading on `/display` gets a 404 instead of the player.
`frontend/nginx.conf` does this; replicate it on any other server.

### Database server settings

The application writes UTC and sets its own session mode on every connection,
so it is safe even on a server configured otherwise. Still, prefer:

```ini
default-time-zone = '+00:00'
sql-mode = STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION
character-set-server = utf8mb4
collation-server = utf8mb4_unicode_ci
```

> XAMPP's MariaDB ships **without** `STRICT_TRANS_TABLES`, which silently
> truncates oversized values instead of raising — exactly the wrong behaviour
> for a DECIMAL rate. `app/db/session.py` forces it per connection, so the
> application is safe regardless; setting it on the server protects anything
> else touching the same database.

---

## Backup and restore

Database and media are **one set**. A database backup without the matching
media leaves versions pointing at files that no longer exist.

### Backup

```powershell
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
New-Item -ItemType Directory -Force "backups\$stamp" | Out-Null

C:\xampp\mysql\bin\mysqldump.exe -u root --single-transaction --routines `
    pam_rate_board > "backups\$stamp\pam_rate_board.sql"

Compress-Archive -Path storage\media -DestinationPath "backups\$stamp\media.zip"
```

`--single-transaction` keeps the dump consistent without locking writers out.

### Restore

```powershell
C:\xampp\mysql\bin\mysql.exe -u root -e "DROP DATABASE IF EXISTS pam_restore_test; CREATE DATABASE pam_restore_test CHARACTER SET utf8mb4;"
Get-Content "backups\<stamp>\pam_rate_board.sql" | C:\xampp\mysql\bin\mysql.exe -u root pam_restore_test
Expand-Archive "backups\<stamp>\media.zip" -DestinationPath restore-check\
```

### Verify the restore — do not assume it worked

```powershell
# 1. Row counts look sane
C:\xampp\mysql\bin\mysql.exe -u root pam_restore_test -e `
  "SELECT (SELECT COUNT(*) FROM rate_versions) AS versions,
          (SELECT COUNT(*) FROM media_assets)  AS assets,
          (SELECT COUNT(*) FROM displays)      AS displays;"

# 2. Schema is at the expected migration
C:\xampp\mysql\bin\mysql.exe -u root pam_restore_test -e "SELECT * FROM alembic_version;"

# 3. Every ready version's media file actually exists, and its checksum matches
$env:DATABASE_URL = 'mysql+pymysql://root:@127.0.0.1:3306/pam_restore_test?charset=utf8mb4'
cd backend
python -m app.cli check
```

A restore that passes the row counts but fails the file check means the media
archive and the dump came from different moments. Take both again.

---

## Health and monitoring

- `GET /health` — liveness. Deliberately loads no OCR model, so it stays fast.
- `GET /api/dashboard` — displays online/offline, stale displays, failed jobs.
- Watch **failed jobs** and **stale displays**: both mean a TV is showing
  something other than what was intended.

---

## Troubleshooting

### OCR fails with `OneDnnContext does not have the input Filter`

PaddlePaddle was upgraded. `paddleocr 2.7.3` does not work with `paddlepaddle 3.x`.

```powershell
pip install "paddlepaddle==2.6.2"
```

Environment workarounds (`FLAGS_use_mkldnn=0`, `FLAGS_enable_pir_api=0`) do
**not** help — this was tested.

### OCR is slow on the first request

PaddleOCR downloads ~16 MB of models on first use into `%USERPROFILE%\.paddleocr`.
Keep that directory; in Docker it is the `paddle_models` volume.

### A version is stuck in `generating`

Retry the save with the same data and idempotency key. New saves render inside the API. For an interrupted or pre-upgrade queued version, inspect `python -m app.maintenance recover-png --version-id ID`, then add `--apply` after stopping the old worker. See the direct-PNG guide for hosting limits.

### Port 8000 already in use

```powershell
netstat -ano | Select-String ":8000"
Get-Process -Id <PID>
```

An older `uvicorn main:app` from before the restructure is the usual culprit.

### `alembic upgrade head` fails

Check `DATABASE_URL` and that the database exists. To inspect without applying:

```powershell
alembic current
alembic history
alembic check     # does the schema still match the models?
```

### A device cannot connect

1. Can the TV reach the API at all? Open `http://<server>:8000/health` on it.
2. Was it revoked? A revoked display shows *dicabut* in the admin table and
   must be paired again.
3. Pairing codes expire after 10 minutes and are single use. The screen
   refreshes them automatically.
4. `VITE_API_BASE_URL` baked into the build must be reachable **from the TV**,
   not just from the developer's machine. `localhost` will not work.

### A TV shows an old board

Compare **Diminta** and **Dilaporkan** in the Display table.

- Same → the TV is showing what was asked for.
- Different → it has not finished; check **last error** on that row.

Use **Refresh** to force a reload. If it is offline it will converge on
reconnect — that is by design, not a failure.

### Offline behaviour in the browser

A TV keeps its last board through an outage and a reload. To confirm, open
DevTools → Application → Cache Storage and look for `pam-player-media-v1` and
`pam-shell-v1`. After changing the service worker, the TV needs one online
reload to pick it up.

### Revoking a device does not take effect instantly

It takes effect the moment the device next contacts the server. A TV that is
currently offline keeps showing its last media until it reconnects. No server
can reach into a disconnected device, and nothing here pretends otherwise.

> **Never** disable Windows Defender or your antivirus to fix a file-lock or
> install problem. If a file is locked, find the process holding it
> (`Get-CimInstance Win32_Process`) and stop that.

---

## Security checklist

- [ ] `SECRET_KEY` set, unique per environment, not in source control
- [ ] `ENVIRONMENT=production`
- [ ] `CORS_ORIGINS` lists exact origins, no wildcard
- [ ] HTTPS/WSS terminated at the proxy
- [ ] Database on a private network, dedicated user, not `root`
- [ ] `.env` not committed (`.gitignore` covers it)
- [ ] Bootstrap admin password changed from whatever was used to install
- [ ] Backups run and a restore has actually been verified
- [ ] `storage/` on a durable volume, included in backups
