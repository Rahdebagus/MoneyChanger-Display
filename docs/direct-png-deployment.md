# Direct PNG release: deployment and rollback

This release is prepared locally. No production deployment, production migration,
credential change or Passenger configuration replacement has been performed.

## What changes

OCR -> edit -> POST /api/versions -> commit rates and retry receipt -> Pillow PNG
and thumbnail -> atomic rename -> ready commit -> success. Publish to TV remains
an explicit action. Standard saves do not require Cron, a queue worker, FFmpeg,
Node on the host, or a spawned Python process.

The new additive migration `3a8c7b19d204` creates `save_requests` and its indexes.
It follows `d15dba763f15`. It does not alter existing accounts, rates or media.
The legacy `mp4_asset_id` database column remains; `mp4_url` is always null.
The response keeps `job: null`. Deploy the new frontend with the new backend;
an old frontend expecting `job.id` is not compatible with direct saves.

## Prepare locally or in CI

From `frontend/`, with Node installed locally:

```bash
npm ci
npm test
npm run lint
npm audit --omit=dev
npm run build
npm run build:cpanel
```

`build:cpanel` produces `deploy/frontend/` in the checkout. It defaults to
`https://puspasarirate.my.id/python-test` and disables application WebSockets.
It removes only old generated assets in that checkout's release folder. Override
`VITE_API_BASE_URL` explicitly if building for a separate staging host. Inspect
the resulting bundle before committing it. No npm command is needed on cPanel.

Review `git diff` and commit the backend, frontend source, migration, bundled
flags, documentation and `deploy/frontend/` together. Do not add `.env`, storage,
uploads or a virtualenv. Push only when the maintenance window is arranged.

## Back up and update the installed backend

Stop writes during the backend/frontend cutover, and stop the **old** generation
worker/Cron entry. Record the previous application commit and static bundle.
Take the hosting provider's database backup and back up the installed code.
Do not replace `.env`, `passenger_wsgi.py`, `.htaccess`, the virtualenv or storage.

Git pull and `.cpanel.yml` update the repository/static frontend; they do not
necessarily update the separately installed FastAPI application in `rateboard_test`.
Verify the real application root and activate the existing Python environment
using the command shown by cPanel's Python application page. The example below
assumes `app/`, `assets/` and `alembic.ini` are directly inside that root. If the
installed layout differs, adjust the paths before running it.

```bash
REPO=/home/puspasarirate/repositories/MoneyChanger-Display
APP=/home/puspasarirate/rateboard_test
test -d "$REPO/backend/app" && test -f "$APP/passenger_wsgi.py" && test -d "$APP/app" || exit 1
BACKUP="$HOME/rateboard-code-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP"
cp -a "$APP/app" "$APP/assets" "$APP/migrations" "$APP/alembic.ini" "$APP/requirements.txt" "$BACKUP/"
python -m pip freeze > "$BACKUP/python-packages.txt"

# Copy only application code and shipped assets. No whole-directory --delete.
cp -a "$REPO/backend/app/." "$APP/app/"
cp -a "$REPO/backend/assets/." "$APP/assets/"
cp -a "$REPO/backend/migrations/." "$APP/migrations/"
cp "$REPO/backend/alembic.ini" "$REPO/backend/requirements.txt" "$APP/"
cd "$APP"
python -m pip check
alembic current
alembic upgrade head
```

Use the existing configured `DATABASE_URL`, `STORAGE_DIR`, `ASSETS_DIR` and
`SECRET_KEY`. Confirm `alembic current` refers to the intended production database
before upgrading. If it is unstamped or differs from the expected migration chain,
stop and reconcile the schema; do not blindly stamp/drop/recreate tables.

The core requirements only remove `imageio-ffmpeg`; there is no new required
runtime dependency for direct PNG. Existing installations need not reinstall all
packages or uninstall shared packages. Keep PaddleOCR **2.7.3** and PaddlePaddle
**2.6.2**. `requirements-passenger.txt` records the adapter version tested locally;
compare it with the host's working adapter before choosing to change it.

If `ASSETS_DIR` points elsewhere, copy the shipped `flags/` there too, alongside
the existing template/logo. Retain existing fonts: output can differ between
Windows Arial and Linux DejaVu even though drawing coordinates are unchanged.

## Shared-host resource profile

Merge only these settings through cPanel's application environment editor. Keep
credentials and existing paths untouched; do not copy `.env.example` over `.env`.

```dotenv
REALTIME_ENABLED=false
DB_POOL_SIZE=2
DB_MAX_OVERFLOW=0
DB_POOL_TIMEOUT_SECONDS=5
REQUEST_THREAD_LIMIT=4
PNG_LOCK_TIMEOUT_SECONDS=2
PNG_RENDER_BUDGET_SECONDS=20
OCR_CPU_THREADS=1
OMP_NUM_THREADS=1
OPENBLAS_NUM_THREADS=1
MKL_NUM_THREADS=1
DISPLAY_TIMEZONE=Asia/Makassar
```

Prefer one Passenger application process where hosting controls allow it. These
limits apply per process except the MariaDB PNG lock, which is shared across
processes using the same database. One OCR engine still consumes substantial
memory; do not increase process count to work around a slow first OCR request.
Keep/prewarm the existing OCR models during the maintenance window if necessary.
The local first engine load plus single-image/three-crop smoke checks took about
47 seconds. PNG rendering stayed fast because it never loaded that engine; the
host still needs enough request time and memory for its first OCR request.

Use the existing Passenger startup configuration and restart through cPanel.
`backend/deployment/passenger_wsgi.example.py` is a reference, not a replacement.
The API sets its AnyIO limiter from HTTP middleware because the tested a2wsgi
adapter does not send ASGI lifespan events. WebSocket fan-out and outbox writes
are disabled in this profile; TV updates use the database through HTTP.

## Deploy the frontend and check

After the backend migration/restart succeeds, update the Git checkout through
cPanel and deploy the reviewed frontend commit. The existing `.cpanel.yml` copies
only `deploy/frontend/` into `public_html`; it remains unchanged. cPanel supports
different push/pull deployment flows; confirm which hook your repository uses
before pushing. [cPanel Git deployment guide](https://docs.cpanel.net/knowledge-base/web-services/guide-to-git-deployment/).

Preserve the existing SPA rewrite and the `/python-test` Passenger mount. Do not
copy a generic `.htaccess` over either. Upload assets before `index.html` if
deploying manually. Reload the admin browser once after cutover.

Check health, login, save, PNG download, history, publish and an actual TV:

```bash
curl --fail https://puspasarirate.my.id/python-test/health
```

A save must return HTTP 201 with `version.status=ready`, a usable `png_url`, and
`job=null`. A duplicate retry with the same key must return the same version ID.
There should be no new generation jobs and, in polling mode, no new outbox rows.
Check API logs for `PNG ready ... render_seconds=...` and host CPU/RAM/process usage.

## Interrupted saves and old queues

A timed-out browser request may already have committed rates. Retry the same
data in the same editor; the key survives a response loss in session storage.
Changing the data creates a new save identity. A hard process kill may leave
`generating`; the same key retries that version after the database releases its lock.
For a legacy queued version or an operator recovery, stop the old worker and run:

```bash
cd "$APP"
python -m app.maintenance recover-png --version-id 123
# Review the selected version, then render that stored version in this process:
python -m app.maintenance recover-png --version-id 123 --apply

python -m app.maintenance cancel-legacy-video --limit 100
# Optional: cancel obsolete queued/expired video work; keep old media and versions.
python -m app.maintenance cancel-legacy-video --limit 100 --apply
```

Recovery never invokes the queue worker and refuses an unexpired active job.
If hosting kills requests before rendering can complete reliably, keep the saved
data and use this bounded-concurrency operator command during a quiet period.
There is no automatic subprocess/background-thread fallback. If even that cannot
complete within the host's CPU/memory limits, the hosting allocation must change.

## Optional cleanup and scheduled publication

Immediate publishing and normal PNG saves work without a scheduler. Future
publication still needs an external scheduler; otherwise the row remains
scheduled. Disk reclamation after history deletion uses durable `cleanup_media`
jobs so a failed deletion transaction cannot remove live files. Run maintenance
explicitly or schedule a non-overlapping one-shot invocation:

```bash
cd "$APP"
python -m app.workers.runner --once --max-jobs 10
python -m app.maintenance cleanup --limit 500 --older-than-days 30
# Dry-run is the default; apply only after reviewing candidate counts.
python -m app.maintenance cleanup --limit 500 --older-than-days 30 --apply
```

If the host supplies `flock`, a Cron entry can use its own interpreter path and
the already configured application environment:

```cron
* * * * * cd /home/puspasarirate/rateboard_test && /usr/bin/flock -n /home/puspasarirate/rateboard-maint.lock /ABSOLUTE/EXISTING/VENV/bin/python -m app.workers.runner --once --max-jobs 10 >> /home/puspasarirate/rateboard-maint.log 2>&1
```

Replace the interpreter placeholder with cPanel's actual path and rotate the log.
This optional job handles schedules/cleanup, never normal PNG generation.
The cleanup command limits each table's batch, keeps unexpired events and pending
jobs, and removes only expired outbox rows, old terminal jobs, expired pairing
codes, and old deleted-version receipts. It never automatically deletes rate
history, accounts, branches, display assignments or uploaded media.

The prior event amplification came from treating device ACK/state updates as
new assignment notifications: read assignment -> ACK -> notify -> read again.
State events and assignment events are now separate, repeated ACKs are no-ops,
and the player ignores state-only notifications. Polling mode also stops the
outbox writer/pump entirely. Cleanup is not the fix for that loop.

## Timeout limits and remaining trade-offs

Local baseline: 12 renders, unchanged 130,600-byte PNG, warm median about 54 ms
versus 97 ms before caching. Local a2wsgi save plus PNG delivery took about
0.19 seconds. These measurements are not shared-host latency guarantees.

Pool acquisition is limited to 5 seconds, PNG lock acquisition to 2 seconds,
database connect to 5 seconds and socket reads/writes to 15 seconds. InnoDB row
lock waits are limited by the socket timeout as a last resort. The frontend
save request aborts after 45 seconds and retains its retry identity.

The 20-second render budget is checked after Pillow returns. Python cannot
safely interrupt an arbitrary C operation or stalled filesystem syscall inside
a request thread. Finite image sizes, offline assets and bounded concurrency
make normal rendering small; they are not a hard execution-time guarantee.
Ask the host to confirm its actual request/CPU/memory/process limits and leave
headroom above the observed save latency. Passenger's `PassengerMaxRequestTime`
is an Enterprise setting, not a portable LiteSpeed/cPanel guarantee.
[Passenger configuration reference](https://www.phusionpassenger.com/docs/references/config_reference/apache/).

`ASGIMiddleware(wait_time=...)` limits waiting for background tasks after the
response; it does not impose a render timeout. No response is sent as success
until PNG readiness has committed.
[a2wsgi documentation](https://github.com/abersheeran/a2wsgi#asgimiddleware).

TV heartbeats run every 30 seconds, assignment checks every five minutes, with
one request per poller, offline backoff and hidden-tab pause. Heartbeat responses
trigger assignment retrieval when changed, so a visible TV normally sees a
publication within about 30 seconds without WebSockets. Hidden tabs may become
offline in the dashboard and synchronize when visible again; a kiosk should
keep its display tab foregrounded. Admin refresh uses 60-second polling.

## Rollback

Keep writes paused. Restore the previous backend code/assets and matching static
bundle from the recorded release, then restart Passenger and reload the frontend.
The additional receipt table can remain; do not downgrade/drop it merely to roll
back code. Legacy columns were retained for compatibility. If restoring an old
queue-based backend, its matching old worker is required again. Do not restore
an old database backup over newer rates unless that data loss is explicitly
intended. Preserve `.env`, credentials, virtualenv, Passenger configuration and
all uploaded/generated media throughout rollback.
