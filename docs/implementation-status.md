# Implementation Status — PAM Rate Board & Remote Display

Working log across sessions. Specification:
[../COPILOT_IMPLEMENTATION_PLAN.md](../COPILOT_IMPLEMENTATION_PLAN.md)

**State: stages 1–8 complete**, with the limitations listed at the end.

---

## Stage 1 — Audit & baseline (done)

### Repository at audit time (2026-10-17)

- **Version control is split.** The project root is *not* a Git repository, but
  **`frontend/` is one**, with an `origin/main` remote and history. The root-level
  check reported "not a git repository" and the nested repo was only noticed
  later, during final verification. Nothing was reset, force-checked-out or
  committed at any point; every deletion was additionally backed up by hand to
  the session scratchpad, outside the project.
- `frontend/.gitignore` was already missing from the working tree before this
  work started (it still exists in `HEAD`). Restored and extended, so
  `node_modules/` and `dist/` are ignored again.
- Initial shape: `backend/` (6 flat modules), `frontend/` (React + Vite),
  **three** virtual environments.

### Entry points before the restructure

| Component | Command | Source |
| --- | --- | --- |
| Backend | `uvicorn main:app --reload --port 8000` | `backend/README.md` |
| Frontend | `npm run dev` → http://localhost:5173 | Vite 8 |
| Docker | `CMD ["uvicorn", "main:app", ...]`, port 7860 | `backend/Dockerfile` |

### Runtime

- Python **3.10.11** (`.venv`), Node **22.22.2**, npm **8.15.0**
- Local database: **MariaDB 10.4.32** from XAMPP — *not* MySQL. Not running at
  audit time (connection refused, error 2002). It speaks the MySQL protocol, so
  `mysql+pymysql` works; the differences that mattered are recorded below.

### Critical finding: OCR was broken

`paddlepaddle 3.3.1` was installed alongside `paddleocr 2.7.3`. A real OCR run
failed:

```
NotFoundError: OneDnnContext does not have the input Filter.
[operator < fused_conv2d > error]
```

`FLAGS_use_mkldnn=0` and `FLAGS_enable_pir_api=0` were both tried and did not
help. Downgrading to `paddlepaddle==2.6.2` — the combination the owner was
already moving towards — was **verified by an actual OCR run**, not assumed:

```
RAW OCR: ['USD','16.950','AUD','12.050','EUR','19.900','GBP','23.000',
          'CHF','21.600','JPY','105,25','SGD','13.225','CAD','12.275']
parsed : USD 16950, AUD 12050, EUR 19900, GBP 23000, CHF 21600,
         JPY 105.25, SGD 13225, CAD 12275
timing : import 5.27 s, OCR one block 3.59 s
```

Locked in `requirements.txt`: **Python 3.10.11 + paddleocr 2.7.3 +
paddlepaddle 2.6.2 + opencv 4.6.0.66**.

### Baseline captured before any change

| Artefact | Value |
| --- | --- |
| `baseline_rates.json` | 22 synthetic currencies including `USD_T`, `USD_K` |
| `baseline_board.png` | 130,600 bytes, sha256 `c57cec98b5…3feaec7` |
| `ocr_left_block.png` | synthetic 8-row OCR fixture |
| venv manifests | `pip freeze` of all three environments |

All three now live in `backend/tests/fixtures/` and are asserted on every run.

### Frontend baseline

- `npm run build` succeeded: `index.js` 237.64 kB (73.67 kB gz), CSS 6.94 kB,
  and **`pam_logo.png` 2,161.87 kB** — one asset was ~90% of `dist/`.
- `npm run lint` **failed with 6 errors**, all pre-existing.

---

## Stage 2 — Restructure (done)

`backend/app/` package; entry point is now **`app.main:app`**. `Dockerfile`,
`README`, `docker-compose.yml`, `alembic.ini` and `.vscode/settings.json` were
all updated; no documentation still refers to `main:app`.

**The generator output is byte-identical.** Verified immediately after the move
and on every test run since:

```
baseline  sha256 c57cec98b55f32cb5a95216b539de8de1dc063fff4fd5a9a0ab5e35aa3feaec7
relocated sha256 c57cec98b55f32cb5a95216b539de8de1dc063fff4fd5a9a0ab5e35aa3feaec7
IDENTICAL
```

---

## Stages 3–6 — Database, auth, versions, displays, publishing (done)

15 tables, one Alembic migration, verified to **upgrade → downgrade → upgrade**
cleanly on a fresh database.

Two MariaDB 10.4 specifics shaped the design:

1. **No `SKIP LOCKED`** (added in 10.6). Job and schedule claiming use a guarded
   `UPDATE ... WHERE status = <expected>` and check `rowcount == 1` instead.
2. **XAMPP ships without `STRICT_TRANS_TABLES`**, which silently truncates
   oversized values — wrong for a DECIMAL rate. The app now sets strict mode and
   `time_zone = '+00:00'` on every connection.

Two bugs found and fixed while building:

- Alembic emitted the cyclic `displays ↔ publication_targets` foreign key inline
  inside `create_table`, where `use_alter` is ignored, so it was **silently
  never created**. Moved to an explicit `op.create_foreign_key`.
- `publication_targets.state` had both a column-level `index=True` and a
  composite index that auto-named to the same thing, which made
  `create_all` fail. The composite index was renamed.

---

## Stage 7 — Cleanup, optimisation, docs (done)

See [cleanup-report.md](cleanup-report.md). Headline: **~2.5 GB freed**, board
generation **7.26 s → 0.09 s** with identical output, `dist/` **2,406 KB → 324 KB**.

---

## Stage 8 — Acceptance checks

Verified in a real Chrome (Playwright driving the installed browser), against
the running stack.

| Check | Result |
| --- | --- |
| Identical fixture produces a board identical to baseline | **pass** — byte-for-byte, asserted in CI |
| Board resolution unchanged (1280×720) | **pass** |
| OCR modes, manual edit, USD T/K, custom logo/title | **pass** |
| Download PNG / MP4 still work | **pass** |
| Two concurrent generates do not overwrite each other | **pass** — separate asset ids, keys and bytes |
| Save does not change what a TV shows | **pass** |
| Publish only accepts a *ready* version | **pass** — 400 otherwise |
| Staff cannot publish or read another branch via the API directly | **pass** — 403 on all five routes |
| Device token cannot reach any admin API | **pass** — 401 on all five routes |
| Pairing code expired / used / replayed is rejected | **pass** |
| Failed login reveals nothing about the account | **pass** — identical message and status |
| Editing a live version creates a new version | **pass** — v1 stayed live and unmodified |
| Rollback is traceable and moves forward | **pass** — new publication, revision 3, never reusing 1 |
| Two displays can hold different versions | **pass** |
| A late update cannot replace a newer one | **pass** — stale ack dropped |
| Retried publish does not double-apply | **pass** — one publication, one target |
| Failed media keeps the previous board and reports failure | **pass** |
| Offline reload works; expiry applied; reconnect resyncs | **pass** — against the production build |
| Schedule survives restart, cancel works, no double publish | **pass** |
| Migration on a fresh database, upgrade path intact | **pass** |
| Backend tests | **pass** — 40 tests, ~11 s, stable over 5 runs |
| Frontend lint / build | **pass** — 0 errors (13 warnings), build clean |
| Clean install from the lockfile | **pass** — verified in a clean directory |
| Visual confirmation, desktop browser | **pass** — all 9 screens, 0 page errors |
| Visual confirmation, physical TV | **not done — see limitations** |

### The end-to-end run, through the UI

```
1. TV opens /display                → pairing code shown
2. Admin pairs the code             → display created, branch Kuta
3. TV claims its own credential     → "Perangkat siap"
4. Upload fixture → OCR             → editor populated
5. Generate & Save                  → version v1, preview 1280x720
6. Tampilkan ke Display             → published
7. TV displays the board            → <img> 1280x720, object-fit: contain
8. Admin: desired v1 rev 1 == reported v1 rev 1, state "displayed"
   page errors: 0
```

Offline, against the production build:

```
board showing while online              : true (1280x720)
board still showing after going offline : true
board restored after an offline RELOAD  : true (1280x720)
board showing after reconnect           : true
```

---

## Measurements

| | Before | After |
| --- | ---: | ---: |
| Board generate (cold / warm) | 7.26 s | 0.25 s / **0.09 s** |
| OCR, one block | 3.59 s | 3.59 s (unchanged) |
| `dist/` total | ~2,406 KB | ~324 KB |
| Main JS chunk | 237.6 KB (73.7 gz) | 233.9 KB (75.2 gz) |
| Player route extra | — | 12.3 KB (4.6 gz) |
| Repository on disk | 4,096 MB | 1,564 MB |
| Source only | ~1.5 MB | ~1.5 MB |
| Backend tests | none | 40, ~11 s |

The main chunk grew by ~4 KB raw because the app gained routing, auth and seven
pages. Stated rather than hidden.

---

## Limitations and outstanding items

1. **No physical TV was tested.** All display verification used Chrome at
   1280×720. Smart-TV browsers vary in codec support, Cache Storage quota and
   kiosk behaviour. **Verification on the real device is pending** — no claim is
   made about compatibility with any particular TV.

2. **`backend/venv` is 373 MB of locked remnants.** It was partially deleted
   while VS Code's language server and an old uvicorn still had it open — the
   pre-delete check covered file references but not running processes. The
   environment is reproducible from the backed-up manifest, `.venv` and the
   running application were unaffected. Finish with
   `scripts\finish-venv-cleanup.ps1` after closing those processes.
   Full detail in [cleanup-report.md](cleanup-report.md).

3. **`frontend/node_modules` was wiped once** by `npm ci --dry-run`, which
   removes the tree before it fails. Restored with `npm install`; lint, build and
   tests all pass. No lasting effect, recorded for completeness.

4. **Rate limiting is per process.** `app/core/ratelimit.py` is in-memory, so
   with several API processes the effective limit multiplies. Pairing codes have
   a second, database-backed attempt counter that does survive multiple
   processes. Replace with a shared store if the API is scaled widely.

5. **Websocket fan-out polls a database table** every 2 s per API process. Correct
   across processes, but move to real pub/sub beyond a handful of them.

6. **Legacy endpoints now require authentication.** The originals were open.
   This is a deliberate, documented deviation — see
   [architecture.md](architecture.md#legacy-endpoints).

7. **Pre-existing dead styling.** Many components carry
   `"@media (min-width: 640px)": {...}` inside React inline `style` objects,
   which React does not support, so they have never applied and the browser logs
   a warning. Left alone: implementing them would change the responsive layout,
   which is a design decision, not cleanup.

8. **13 lint warnings** from `react-hooks/set-state-in-effect`, the React
   Compiler rule that flags ordinary fetch-on-mount. Downgraded to a warning
   with the reasoning recorded in `frontend/eslint.config.js`, not switched off.

9. **MP4 playback on a TV is untested.** The encode and download path is
   verified; whether a given TV decodes the H.264 file is device-specific. The
   player falls back to the PNG, which is what publishes by default.
