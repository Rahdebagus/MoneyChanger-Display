# Direct PNG implementation report

Validation completed locally on 25 October 2026. Production was not deployed.

## Result and flow

The save endpoint now commits edited rates and a retry receipt, renders the
1280 x 720 PNG and thumbnail with Pillow inside FastAPI, validates/writes the
files atomically, commits `ready`, and returns the finished version. No PNG job
is queued and no worker, Cron or subprocess is launched by saving. Publishing
still requires a separate explicit action.

Repeated clicks share one frontend request. Lost responses can be retried with
the same stored key; backend receipts are scoped to the user and payload. Busy
renderers return 503, conflicting payloads return 409, and deleted-version
receipts return 410. Failed rendering retains rates and a useful error, with a
same-version retry. A database advisory lock bounds concurrent rendering across
Passenger processes; row locks protect version numbering and receipt state.

## Main files

| Area | Added or changed files |
| --- | --- |
| Save service | `backend/app/services/direct_save.py`, `access.py`, `rates.py`, `board_builder.py`, `storage.py` |
| API and sessions | `backend/app/api/routes/{versions,media,device_api,ocr,legacy}.py`, `api/deps.py`, `api/serializers.py`, `db/session.py`, `main.py` |
| Idempotency | `backend/app/models/save_request.py`, model exports, schemas, `backend/migrations/versions/3a8c7b19d204_save_receipts.py` |
| Rendering/OCR | `backend/app/services/{generator,ocr,ocr_runner}.py`, 20 PNG flag assets under `backend/assets/flags/` |
| Maintenance | `backend/app/maintenance.py`, `workers/runner.py`, `services/{events,publishing,version_cleanup}.py`, job model/enums |
| Hosting/config | `.env.example`, `backend/app/core/config.py`, `backend/requirements.txt`, `backend/requirements-passenger.txt`, `backend/Dockerfile`, `docker-compose.yml`, reference-only `backend/deployment/passenger_wsgi.example.py` |
| Editor/preview | `frontend/src/hooks/useRateBoard.js`, `utils/saveRequest.js`, `services/apiClient.js`, `pages/RateBoardPage.jsx`, `components/Steps/Step3_Preview/GeneratedDesignPreview.jsx` |
| History/TV | `frontend/src/features/history/HistoryPage.jsx`, `features/player/{PlayerPage,PairingScreen}.jsx`, `features/player/mediaCache.js` |
| Build | `frontend/scripts/build-cpanel.mjs`, package script, ESLint config, frontend environment example, regenerated `deploy/frontend/` |
| Tests | `backend/tests/test_direct_save.py`, publishing/history tests and fixtures setup, `frontend/tests/saveRequest.test.js` |
| Documentation | README, architecture/deployment guides, this report; earlier reports marked historical |

## Removed video functionality

Removed FFmpeg invocation, `imageio-ffmpeg` requirement, Docker FFmpeg package,
video configuration, video builder, active generation job types/handlers,
`/generate-video`, `/api/versions/{id}/video`, download/preview controls and TV
video playback. Old video assets are not served or included in assignments.
Legacy database columns and the null response field remain to avoid destructive
migrations. Explicit maintenance can cancel obsolete video jobs; it preserves
existing media and rate records.

## Performance and storage

All flags are bundled locally, eliminating first-render CDN waits. Fonts,
scaled flags and the background are cached with fixed bounds; drawing uses a
private background copy. Byte-for-byte regression confirms the approved PNG
composition is unchanged on the tested font environment.

The MariaDB pool defaults to two connections with zero overflow and a finite
acquisition timeout. FastAPI's request thread limiter defaults to four. OCR
remains lazy, with one inference slot per process, a one-second busy timeout,
one CPU thread by default, finite upload/pixel limits and sequential crops.
PaddleOCR 2.7.3 / PaddlePaddle 2.6.2 remain pinned.

PNG saves no longer create job/event traffic. The previous ACK notification loop
was addressed by separate assignment/state events and idempotent ACK handling;
the Passenger polling profile disables outbox writes/pump entirely. TV heartbeat
is 30 seconds, full sync five minutes; hidden/offline tabs pause polling. Old
outbox/terminal job/expired pairing/deleted receipt cleanup is explicit and
bounded. History deletion retains safety checks and durable media cleanup.

Local renderer comparison (12 renders, same 130,600-byte output):

| Renderer | First render | Warm median |
| --- | ---: | ---: |
| Previous | 143.36 ms | 96.61 ms |
| Direct PNG/cache | 123.03 ms | 53.63 ms |

One Python thread existed before wrapping a2wsgi; saving did not import Paddle.
The actual a2wsgi HTTP save + authenticated PNG check took approximately 0.189 s
with `/python-test` as `SCRIPT_NAME`, without ASGI lifespan or a worker.

## Executed verification

- Backend: **77 passed** against dedicated MariaDB test data. Covers rates,
  ready/file validation, render errors, duplicate/concurrent saves, commit
  rollback/uncertain commit, user scope, history restrictions, publication,
  authentication, no video endpoints/downloads, maintenance and OCR admission.
- Frontend: **8 passed**; duplicate requests, retry identity, reload, incomplete
  responses, abort and polling behavior. ESLint passed.
- Production Vite build passed. `npm audit --omit=dev`: **0 vulnerabilities**.
- `npm run build:cpanel` passed and refreshed the static bundle in `deploy/frontend/`.
- Additive Alembic upgrade verified on a separate database, preserving an
  existing account and legacy columns. No production migration was executed.
- Chrome browser smoke passed: open-as-new, two clicks/one save, immediate PNG
  preview, authenticated download, publish dialog, polling TV with application
  WebSockets disabled, cached PNG reuse, and deletion of unused history.
- Browser testing exposed a Strict Mode race clearing open-version navigation
  state too early; the cancelled effect now leaves it alone.
- Actual PaddleOCR single-image and three-block inference passed with the
  existing local models and one CPU thread configured. First engine load plus
  both checks took 47.29 seconds; PNG-only requests do not pay that cost.
- The additive migration was also applied to the existing **local** project
  database. Account/rate/display counts were checked unchanged. Local API health
  and the frontend login page returned success on ports 8000 and 5173.

The first resumed test attempt found local MariaDB stopped; after restarting
the local service, the full 77-test suite passed. Dependency notices about
pytest-asyncio fixture scope and Node MockTimers are non-failing existing notices.
The browser and OCR checks ran locally, not on a physical television or the
production LiteSpeed process. Production OCR cold-start time and resource
availability still need a deployment smoke check.

## Migration, deployment, rollback and limits

Follow [the deployment guide](direct-png-deployment.md) for exact local build,
cPanel/backend copy, `alembic upgrade head`, optional cleanup/scheduler and
rollback commands. Git/static deployment does not update an independent
`rateboard_test` installation automatically. Existing `.env`, credentials,
Passenger startup/rewrite files, virtualenv and uploads must be preserved.

The migration only adds `save_requests`. Roll back matching frontend/backend
code while leaving that table in place; no destructive downgrade is required.

Scheduled publication and deferred disk cleanup still require explicit
maintenance or an external scheduler. Normal save/immediate publication do not.
The 20-second render budget is a **soft** check after Pillow returns, not a hard
C-call/filesystem timeout. The client aborts after 45 seconds while preserving
retry identity. Host resource/request limits must be measured on production.
The explicit `recover-png` command is the supported operator fallback; there
are no uncontrolled background processes or automatic false-success responses.
