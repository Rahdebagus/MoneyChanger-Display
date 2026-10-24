# Cleanup report

Update 2026-10-24: the project now uses one repository at its root for backend
and frontend. The split-repository notes below describe the earlier cleanup.
The previous frontend Git metadata was backed up before this migration.

Everything removed here was verified unused first, and backed up before
deletion. Backups live in the session scratchpad **outside the project folder**:

```
C:\Temp\claude\c--xampp-htdocs-Project-sukunan-money-chager\<session>\scratchpad\
  backup-venv-manifests\     pip freeze of all three virtual environments
  backup-docs\               the 12 Markdown files removed below
  backup-frontend-removed\   the 4 dead JS modules removed below
  backup-assets\             the original 1536x1024 logo
  baseline\                  baseline board PNG, fixture rates, OCR fixture
```

> **Version control is split.** The project *root* is not a Git repository
> (`git rev-parse` fails, there is no `.git/`), but **`frontend/` is its own
> repository** with a remote and history. So deletions under `frontend/` are
> recoverable with `git checkout`, while everything under `backend/` and the
> root is not — which is why every deletion was also backed up to disk by hand.
>
> Nothing was reset, force-checked-out or committed. `frontend/.gitignore` had
> already been deleted from the working tree before this work began; it was
> restored from `HEAD` and extended, because without it `node_modules/` and
> `dist/` showed up as untracked and could have been committed by accident.

---

## Disk

| | Before | After |
| --- | ---: | ---: |
| Whole project | 4,096 MB | 1,564 MB |
| Source only (no venv / node_modules / storage / dist) | ~1.5 MB | ~1.5 MB |

**~2.5 GB freed.** This is disk space, not runtime performance — removing a
virtual environment makes nothing faster. The one measured runtime improvement
is recorded under *Optimisation* below.

---

## Files moved

The backend went from six flat modules to an application package. The entry
point changed, so everything that named it was updated in the same pass.

| Old | New |
| --- | --- |
| `backend/main.py` | `backend/app/main.py` (app factory) + `app/api/routes/*` |
| `backend/generator.py` | `backend/app/services/generator.py` |
| `backend/ocr.py` | `backend/app/services/ocr.py` |
| `backend/parser.py` | `backend/app/services/parser.py` |
| `backend/mapper.py` | `backend/app/services/mapper.py` |
| `backend/preview_generator.py` | `backend/tests/fixtures/` (became the regression fixture) |
| `backend/preview_board.png` | `backend/tests/fixtures/baseline_board.png` |
| `backend/README.md` | root `README.md` + `docs/` |

The flat modules were **copied** into the package first, verified, and only
removed once nothing imported them and the full suite passed against the
package versions. `parser.py` and `mapper.py` are byte-identical to their
originals; `generator.py` and `ocr.py` differ only by the import path and the
asset/flag-cache changes described above.

Updated to match: `backend/Dockerfile` (`CMD` now `app.main:app`),
`README.md`, `docker-compose.yml`, `alembic.ini`, `.vscode/settings.json`.
No documentation still says `main:app`.

> `preview_board.png` and `preview_generator.py` were **not** deleted on the
> strength of their names. They turned out to be the visual fixture for the
> generator, so they were promoted into the test suite, where
> `test_generator_regression.py` now compares every build against that exact
> image byte for byte.

---

## Removed

### Virtual environments — 2,573 MB

Three existed. The project now keeps one: **`.venv`** at the repository root
(Python 3.10.11), which is what the API, the worker and the tests all run on.

| Path | Size | Evidence it was unused | Status |
| --- | ---: | --- | --- |
| `backend/venv_old` | 1,120 MB | Python 3.10.11. No process using it, no reference in any source, config, script or doc. | **Removed** |
| `backend/venv` | 1,453 MB | Python 3.10.4. No reference in any source, config or doc. | **Partially removed — see below** |

Before deleting anything, `pip freeze` from all three was saved to
`backup-venv-manifests/`, and both are reproducible from
`backend/requirements.txt`.

#### `backend/venv` — an incomplete removal, and the mistake behind it

This one was **still in use** when deletion started. The check that was run
covered *file references* (imports, config, scripts, Docker, docs) but **not
running processes**. Two processes had it open:

| PID | What it was |
| --- | --- |
| 6848 | an old `uvicorn main:app --reload --port 8000` from before the restructure |
| 24124 | VS Code's isort language server — VS Code's selected interpreter was `backend/venv` |

Windows blocked the delete partway through, but roughly 1,080 MB had already
gone: `site-packages` dropped from 249 entries to 216 (everything alphabetically
before `chardet`), and `Include/` was removed. The environment is **broken for
new imports**; the already-running processes kept working because their code was
already in memory.

Nothing else was affected — `.venv` and the running application were untouched,
and the environment is fully reproducible from the backed-up manifest.

**Current state: 373 MB left, still locked.** To finish, close VS Code (or
reload it, now that `.vscode/settings.json` points at `.venv`), stop the old
uvicorn process, and run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\finish-venv-cleanup.ps1
```

The script refuses to run while anything still holds the directory open, and
names the processes instead of forcing it.

### Dead frontend modules

| File | Lines | Evidence |
| --- | ---: | --- |
| `frontend/src/utils/rateBoardGenerator.js` | 354 | A second, canvas-based board renderer. Imported by nothing (`grep` across `src/` for the module name and every exported symbol returned no importer). It also drew a *different* board — emoji flags, label `USD T/OLD` — so it was not the generator in use and could only ever have diverged from the real one. |
| `frontend/src/services/api.js` | 82 | Superseded by `services/apiClient.js`. No importer. |
| `frontend/src/services/index.js` | 2 | Only re-exported `api.js`. No importer. |
| `frontend/src/utils/index.js` | 2 | Only re-exported removed modules. No importer. |

A second pass after the frontend was rewritten found more, each confirmed dead
at the **symbol** level (zero references to the exported names anywhere outside
the file itself), not just by filename:

| File | Evidence |
| --- | --- |
| `src/utils/formatters.js` | `formatRate` and `generateRateBoardFilename`: 0 uses. Superseded by `utils/datetime.js` and server-side formatting. |
| `src/hooks/useFileUpload.js` | `useFileUpload`: 0 uses. The upload step manages its own state. |
| `src/hooks/index.js` | Barrel re-exporting the above. No importer. |
| `src/constants/index.js` | Barrel re-exporting `currencies.js`, which every caller imports directly. No importer. |
| `src/assets/hero.png`, `react.svg`, `vite.svg` | Vite starter leftovers. 0 references in `src/` or `index.html`. |

Removing all of these cleared 5 of the 6 pre-existing lint errors, and `lint`
plus `build` were re-run afterwards to confirm nothing depended on them.

### Duplicated documentation — 12 files, ~95 KB

All described the same earlier frontend refactor and the structure it produced,
which this change supersedes. Their useful content — layer conventions, where
things live, how to run the app — is now in `README.md` and
`docs/architecture.md`.

```
frontend/00_START_HERE.md          frontend/FILE_STRUCTURE_GUIDE.md
frontend/ARCHITECTURE_FLOW.md      frontend/QUICK_START.md
frontend/DEVELOPER_CHECKLIST.md    frontend/README_STRUCTURE.md
frontend/DOCUMENTATION_INDEX.md    frontend/REFACTORING_SUMMARY.md
frontend/FILE_INVENTORY.md         frontend/REFERENCE_CARD.md
frontend/README.md                 frontend/src/ARCHITECTURE.md
```

`frontend/README.md` was the unmodified Vite starter text.

`COPILOT_IMPLEMENTATION_PLAN.md` was **kept**: it is the repository's own
instruction document and still applies.

`backend/README.md` was replaced by the root `README.md`. It was also
**factually wrong**: it documented `USD_T = USD - 400` and `USD_K = USD - 3800`,
while `mapper.py` has always used `USD_T = USD - 200` and `USD_K = 14000`. The
code is the source of truth; the formulas were not changed.

### Other

| File | Why |
| --- | --- |
| `frontend/mintty.exe.stackdump` | Terminal crash artifact, 1.3 KB |
| `__pycache__/`, `.pytest_cache/` | Regenerated on demand; now gitignored |

---

## Kept deliberately

| Item | Why |
| --- | --- |
| `backend/assets/pam_bg.png`, `pam_logo.png` | Loaded by the board generator at render time via a config path, not an import. A grep for imports would have shown nothing — they are read by filename. |
| `~/.paddleocr/` (~16 MB) | The active OCR models. Deleting them forces a re-download on next use. |
| `frontend/package-lock.json` | A clean install must be reproducible. `npm ci` requires it. |
| `frontend/node_modules` (84 MB) | Not dead code. Excluded from Git and from the Docker build context instead. |
| `.env` | Local configuration. Gitignored, never deleted. |
| `COPILOT_IMPLEMENTATION_PLAN.md` | Repository instructions, still in force. |

Nothing was removed with a wildcard, `git clean -fdx` was never run, and no
security software was disabled at any point.

---

## Asset optimisation

`frontend/src/assets/pam_logo.png` was **1536×1024, 2,161 KB** — roughly 90% of
the entire production bundle — displayed at most 120 px wide in the header.
Resized to 480×320 (4× the largest display size, so it stays crisp at any DPI):

| | Before | After |
| --- | ---: | ---: |
| Logo | 2,161.9 KB | 47.8 KB (**-97.8%**) |

The original is in `backup-assets/`. This is the **UI chrome logo only**. The
board's own logo is `backend/assets/pam_logo.png`, which was not touched — the
generated board is unchanged, as the byte-for-byte regression test confirms.

---

## Optimisation, measured

| Measurement | Before | After |
| --- | ---: | ---: |
| Board generate, cold | 7.26 s | 0.25 s |
| Board generate, warm | 7.26 s | **0.09 s** |
| Frontend `dist/` total | ~2,406 KB | ~324 KB |
| Main JS chunk | 237.6 KB (73.7 KB gz) | 233.7 KB (75.1 KB gz) |
| Player route payload | main chunk incl. cropper + editor | main + `PlayerPage` 12.3 KB (4.6 KB gz) |
| OCR, one block | 3.59 s | 3.59 s (unchanged) |
| Backend test suite | none existed | 40 tests, ~11 s |

The generate speedup is the on-disk flag cache: the generator used to fetch 20
flag PNGs from `flagcdn.com` on every render. The cached bytes are exactly what
the CDN returned, so the board is byte-identical — and the worker no longer
depends on an external service being reachable.

The player no longer downloads the image cropper, the rate editor or the admin
tables: the generator and every admin page are lazy routes. The main chunk is
essentially React plus the router.

> The main JS chunk grew slightly (+3.9 KB raw) because the app gained routing,
> auth and seven new pages. That is a real cost, stated rather than hidden; the
> 86% drop in total `dist/` size comes almost entirely from the logo.

---

## Still outstanding

1. **`backend/venv` is 373 MB of locked remnants.** Run
   `scripts\finish-venv-cleanup.ps1` after closing VS Code and the old uvicorn.
2. **Pre-existing dead styling.** Many components carry
   `"@media (min-width: 640px)": { ... }` *inside React inline `style` objects*.
   React does not support media queries there, so these have never applied and
   the browser logs `Unsupported style property @media (min-width: 640px)`. They
   were left alone: removing them changes nothing, but *implementing* them would
   alter the responsive layout, which is a design decision rather than a
   cleanup. Listed here so it is a known, deliberate omission.
