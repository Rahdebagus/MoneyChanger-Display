# Architecture

## Request flow

React editor -> authenticated FastAPI save -> MariaDB rates/receipt commit ->
Pillow PNG + thumbnail -> atomic file rename -> ready commit -> preview.
Publish remains a separate authorized action. The API renders in-process;
standard saves create no jobs and launch no processes. The optional worker
handles media cleanup and scheduled publication only.

Passenger uses HTTP polling with REALTIME_ENABLED=false. ASGI deployments may
enable WebSockets. No Node runtime is needed to serve the compiled frontend.

## Rendering and concurrency

The original 1280 x 720 drawing constants, fonts, colors and composition are
unchanged. Flags ship in backend/assets/flags, with the existing storage flag
cache taking precedence. Fonts, resized flags and the template use bounded
in-process caches. A per-request copy protects the cached background.
The regression test compares PNG bytes against the approved fixture.

A MariaDB advisory lock serializes PNG work across Passenger processes. It
waits at most two seconds, then returns a retryable 503. The HTTP session pins
one physical connection across commits so GET_LOCK cannot escape to another
request. RateBoard row locks protect version numbering, including duplicates.

Save receipts hash the actor plus client key and normalized payload. A repeat
returns the original ready version; a failed/interrupted attempt retries that
same version. Changing the payload with an existing key returns 409. Deletion
leaves a tombstone (410 on retry), with optional expiry after 30 days. Old
clients may omit the key but then have no retry deduplication guarantee.

Rates commit before rendering. File writes use flush/fsync + atomic rename.
Readiness commits only after the PNG validates and exists. Failed final commits
roll back media metadata; a retry repairs files. Uncertain commits are reread
before marking failure, so a valid committed PNG is never deleted blindly.
Interrupted requests can be recovered explicitly using app.maintenance.

## Data model

| Table | Holds |
| --- | --- |
| `users`, `branches`, `user_branches` | accounts, branches, staff→branch grants |
| `rate_boards` | one board per branch; the container for versions |
| `rate_versions` | an immutable snapshot: title, subtitle, logo, status, media refs |
| `rate_items` | one row per currency, `DECIMAL(18,4)`, **nullable** |
| `media_assets` | storage key, MIME, checksum, dimensions, size |
| `displays` | a paired TV: credential hash, last seen, desired vs reported revision |
| `pairing_codes` | short-lived, single-use, hashed |
| `publications` / `publication_targets` | one publish action, fanned out per display |
| `jobs` | durable background work with leases and retries |
| `event_outbox` | cross-process websocket notifications |
| `audit_logs` | append-only trail |

### Why rates are nullable DECIMAL

A rate is money, so it is `DECIMAL(18,4)`, never a float. `NULL` means "not
traded today" and renders as `-` on the board. That is deliberately **not** the
same as `0`, which would claim the currency is worth nothing.

The OCR parser returns `0` for a currency it could not read; the API translates
that to `null` before it reaches the editor, so an unreadable row shows an empty
field and a dash on the board rather than a zero rate.

Rates cross the wire as **strings**. A JSON number is a float in every browser,
and `16950.0001` is not a rate anybody typed.

### Why editing never overwrites

A version is immutable once generated. "Edit the board that is on screen"
creates a *new* version with `source_version_id` pointing back. The live board
cannot change underneath a TV, and the history stays truthful.

---

## Authorization

Two principal types that can never be confused, because they are validated by
different code against different columns:

**Users** (admin / staff) authenticate with a signed JWT carrying a `tv`
(token-version) claim copied from their row. Bumping `users.token_version` —
which a password change, a role change or a deactivation does — invalidates
every outstanding token immediately, with no blacklist to maintain.

**Devices** (TVs) authenticate with an opaque 256-bit secret. Only its SHA-256
is stored. Revoking sets `credential_hash = NULL`, so the credential dies the
next time the device contacts the server. A device token can never satisfy a
user dependency, so a TV cannot reach any admin route.

> Device secrets are hashed with SHA-256 rather than bcrypt on purpose: they are
> high-entropy random values, not user-chosen passwords, so there is nothing to
> brute force, and a heartbeat every 30 seconds must stay cheap.

Authorization is enforced per request in `app/api/deps.py`. Hiding a button in
the UI is not access control; `ensure_branch_access` and `ensure_display_access`
are. The test suite calls the API directly as a staff user to prove it.

Bearer tokens in the `Authorization` header were chosen over cookies because the
SPA and the API are separate origins. That sidesteps CSRF entirely. The
trade-off is XSS exposure of the token, mitigated by a bounded TTL and instant
server-side revocation.

Websockets cannot carry an `Authorization` header in a browser, and a token in
the query string would land in proxy logs. The token travels in the
`Sec-WebSocket-Protocol` header instead: `new WebSocket(url, ["bearer", token])`.

---

## Media

Media is private. Every byte goes through `/api/media/{id}` with an
authorization check:

- a **user** may read media of a version in a branch they can access;
- a **device** may read media of any version ever published to it — which is
  what lets a TV refill its cache after a reconnect without a fresh signed URL.

An asset is written once and a new version gets a new id, so URLs are immutable
and carry `ETag` plus `Cache-Control: immutable`. A player polling every 30
seconds re-downloads nothing; a revalidation returns `304`.

Each version writes to `storage/media/versions/<id>/`. Two people generating at
the same time cannot collide — no shared `preview_board.png`.

---

## Maintenance and OCR

Only cleanup_media jobs are claimed by the worker. No PNG or video jobs are
enqueued. Historical generation jobs can be reviewed and recovered explicitly;
they are never executed by the new worker. Worker claims and scheduled
publication retain their guarded updates and leases.

OCR stays lazy: importing the API or saving PNG never imports Paddle. Inference
has one slot per process and rejects busy requests after one second. Paddle,
OpenCV and BLAS CPU threads default to one. Uploads are bounded to 10 MB and
8 million pixels, and cropped blocks are processed sequentially. The verified
PaddleOCR 2.7.3 / PaddlePaddle 2.6.2 pins remain unchanged.

See [deployment and limits](direct-png-deployment.md) for optional maintenance,
soft render budgets, scheduler requirements and explicit interrupted-save recovery.

## The publishing protocol

This is where ordering matters most.

**Revisions.** Each display has a monotonic counter. A publish takes the next
number under a row lock, and `UNIQUE (display_id, revision)` is the backstop.
Two admins publishing at once get distinct, ordered revisions.

**Desired vs reported.** `displays.desired_target_id` is what we asked for;
`reported_revision` / `reported_version_id` is what the TV confirmed. They are
kept separate so a stuck display is visible instead of being averaged away. The
dashboard shows both, and flags the difference as *belum sinkron*.

**The player's update sequence**, in order:

1. read the assignment from the server
2. download the media
3. **validate it by actually decoding it** (`Image.onload` / `video.onloadeddata`)
4. only then swap the picture over
5. acknowledge, carrying the revision and version id

A download or decode failure leaves the previous picture exactly where it was
and reports `failed`, which surfaces on the dashboard. A broken render never
reaches a screen.

**Monotonicity.** An acknowledgement for a revision lower than the display
already reports is dropped. A slow old update cannot replace a newer one.

**Idempotency.** A publish carries an `idempotency_key`; replaying the same
request returns the original publication rather than publishing twice.

**Branch scope** is resolved to concrete displays *at publish time* and never
re-resolved. A TV paired tomorrow does not silently inherit today's publish — it
needs an explicit publish, which is the unambiguous behaviour.

**Rollback** creates a *new* publication with a *new* revision pointing at the
previous ready version. It never rewinds the log or reuses a revision number.

**Refresh** is a one-shot command with an id that is cleared only by an
acknowledgement, so a player cannot read it twice and spin in a reload loop.

> An acknowledgement is evidence about the browser: it decoded the media and
> swapped it in. It is **not** proof that the physical panel is powered on, and
> nothing in this system can prove that.

---

## Scheduling

A scheduled publication stores its target display ids in
`publications.scheduled_display_ids`. The worker polls for due rows and claims
each with a guarded state transition:

```sql
UPDATE publications SET state='active' WHERE id=:id AND state='scheduled'
```

Only one worker can win, so a schedule fires exactly once no matter how many
workers run. Schedules survive restarts because they live in the database, not
in a timer. A past `scheduled_at` means "publish now", not "a schedule that
never fires".

---

## Realtime

Websockets are a latency optimisation, never the source of truth. Every message
means *"something changed, go re-read your assignment"*. A player that misses
one still converges through its 30-second poll, and always re-reads on
reconnect.

Broadcast across processes goes through the `event_outbox` table: any process
appends, and each API process tails the table from its own cursor and pushes to
the sockets it holds. That stays correct with several API processes without
introducing Redis. The cost is up to `EVENT_POLL_INTERVAL_SECONDS` (default 2s)
of latency.

---

## Offline behaviour on a TV

- **App shell** — a service worker (`frontend/public/sw.js`) caches
  `index.html` and the hashed build assets, so reloading while offline still
  boots the player. API traffic is never cached there.
- **Board media** — cached by the player itself in the **Cache Storage API**,
  because binary media is too large for `localStorage` and memory does not survive
  a reload. Eviction is oldest-first and always protects whatever is on screen.
- **Pointer state** — which media, revision and expiry are current is small
  enough for `localStorage`.
- **Expiry** — `valid_until` empty means "show until replaced". Once a stated
  expiry passes, the player switches to a neutral *"Rate sedang diperbarui"*
  screen rather than continuing to show rates it knows are stale.
- **First boot offline, nothing cached** — a clear information screen, never a
  blank or half-drawn board.

---

## API surface

Prefix `/api`. Full schema at `/docs`.

| Area | Endpoints |
| --- | --- |
| Auth | `POST /auth/login`, `/auth/logout`, `GET /auth/me`, `POST /auth/change-password` |
| Users / branches | `GET POST /users`, `PATCH /users/{id}`, `GET POST /branches`, `PATCH DELETE /branches/{id}` |
| OCR | `POST /ocr/upload`, `POST /ocr/upload-blocks` |
| Versions | `POST GET /versions`, `GET /versions/{id}`, `/duplicate`, `/video`, `/archive`, `/restore` |
| Jobs | `GET /jobs/{id}`, `GET /jobs` |
| Media | `GET /media/{id}`, `GET /media/{id}/download` |
| Displays | `GET /displays`, `POST /displays/pair`, `PATCH`, `/refresh`, `/revoke`, `/rollback` |
| Device | `POST /device/pairing/start`, `/status`, `/claim`, `GET /device/assignment`, `POST /device/heartbeat`, `/acknowledge`, `/command-ack` |
| Publications | `POST GET /publications`, `GET /publications/{id}`, `/cancel` |
| Audit | `GET /audit` |
| Realtime | `WS /ws/device`, `WS /ws/admin` |

The database is never exposed to the frontend or to a TV.

### Legacy endpoints

`/upload`, `/upload-blocks`, `/generate`, `/generate-video` are still mounted so
existing callers keep working (`ENABLE_LEGACY_API=false` unmounts them).

**One deliberate difference: they now require authentication.** The originals
were open to anyone who could reach the port. Leaving an unauthenticated OCR and
image-generation endpoint exposed would contradict the requirement that
authorization is enforced on every request, so the shims authenticate while
keeping the request and response formats identical.

---

## Errors

A client never sees a traceback or an internal path. Every response carries a
`request_id` that also appears in the server log line, so a user can quote
"error, ID 3f2a…" and it can be traced. `app/core/logging.py:redact()` strips
anything password-, token- or credential-shaped before it reaches a log or an
audit row.
