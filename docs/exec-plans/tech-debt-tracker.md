<!-- last_verified: 2026-08-04 -->
# Tech Debt Tracker

Known tech debt items. Agents update this when they discover or create tech debt.

## Open

| Description | Impact | Proposed Resolution | Priority |
|---|---|---|---|
| Colorize runner queue and batch-record lock are in-process | Two API replicas would each run their own queue and could interleave writes to one record | Keep one API replica; for scale, move the queue to a shared store and make `batch_store.mutate` a conditional write (ETag `If-Match`) | Medium |
| Photo Library and batch list read every batch record | `list_photos` / `get_stats` scale with the number of batches (records are ETag-cached, but still listed each call) | Maintain a per-original version index object updated by the runner, or paginate batch records | Low |
| Bucket Explorer deletes do not update batch records | Deleting a colorized output by key leaves its batch item pointing at a missing object (broken gallery tile) | Reject explorer deletes under `colorized/`/`comparisons/`, or mark the owning item on delete | Low |
| Download counter & `/metrics` not durable across restart/replicas | Counter resets on redeploy (ephemeral FS); both fragment across replicas | Back the counter with a shared store (Redis/DB); label/aggregate metrics per instance. Relocated to `repo/counter.py` and documented in RELIABILITY.md | Medium |
| Upload buffers the whole file in memory | ~3× file size RAM per upload; large files strain the server (event loop no longer blocked, but memory unbounded) | Stream to a temp file, or S3 multipart above a size threshold | Medium |
| `GET /files-by-key/detail` re-downloads the whole object to recompute metadata | Rich metadata for stored files costs a full download + in-memory hash per preview; large objects are slow/expensive and buffer in API memory | Persist `FileMetadataDetail` at upload (S3 user-metadata, mind the ~2KB cap, or a sidecar/object store) and serve it without re-downloading; add a size ceiling above which detail is skipped | Medium |
| Audio/Video metadata fields declared but never extracted | `duration_seconds`/`codec`/`bitrate` always null; real extraction needs a system dependency (ffmpeg/ffprobe or libmediainfo), not a pip-only lib | Add an audio/video extractor in `service/metadata.py`, or drop the fields from `FileMetadataDetail` | Low |
| `get_upload_activity` re-materializes `FileMetadata` for every object just to bucket dates | Wasted O(n) CPU per `/files/stats/activity` (scan is cached; materialization is not) | Aggregate from raw listing dicts like `get_upload_stats` does | Low |
| `GET /files` has no pagination — `/files` shows only the newest 100 objects | An older object is unreachable from the UI. The browser now *states* the truncation (`lib/file-list-limit.ts`) instead of claiming "everything in your bucket", but there is still no way to page or search to an older key | Add cursor pagination to `GET /files` (pass through S3's `ContinuationToken` rather than slicing a full scan) plus "Load more"/search in `FileBrowser` | Medium |
| Only the tree layout exists on `/files`; the Settings "Default file view" List and Grid options are demo placeholders | Settings offers Tree/List/Grid but only the tree renders; the option is labelled a demo field and persists to localStorage only | Build real List/Grid renderers plus a view switcher on `/files`, then honour the stored `defaultView` and drop the "Demo field" label | Low |
| `/settings` Profile & preference fields are a labelled demo, not backed by real surfaces | Display name, bio, email-on-upload, quota-warning + threshold, and default view are illustrative placeholders (persist to localStorage, drive nothing) because there is no account system, mailer, quota banner, or activity log. Theme is the only real preference | Build each backing surface (mailer, quota banner, activity log / share links, List/Grid views), then wire the matching field to it — server-side behind a `/preferences` route once auth lands — and drop its "Demo field" label | Low |
| Frontend has no component/render tests; e2e only checks routing | UI states (loading/error/empty) and the real upload→delete journey are unverified | Add jsdom + @testing-library/react render tests; a fixture-driven upload e2e | Medium |
| Allowed file types hardcoded in `service/upload.py` | Reuse friction — each new app edits source to change accepted types | Make `ALLOWED_TYPES` / `MIME_EXTENSION_MAP` env-configurable | Low |
| No auth layer or placeholder | Every consumer designs auth from scratch; unclear where it plugs in | Add example middleware (API-key or JWT) + docs for the seam | Low |
| No `docker-compose.yaml` | Manual venv + dual-process startup slows first run | Add compose with `web` + `api` services and Dockerfiles | Low |
| No dedicated connection-status banner | Offline only surfaced reactively per failed query | Add a global connectivity banner (route + global error boundaries already exist) | Low |
| `e2e/**` and `playwright.config.ts` are excluded from `apps/web/tsconfig.json` | Neither `pnpm typecheck` nor `next build` typechecks the E2E specs, and `pnpm test:e2e` is not in CI — type errors there can sit undetected indefinitely | Add a dedicated `tsconfig.e2e.json` and typecheck it in `pnpm verify:web`, or drop the exclude | Low |
| No tests for the ~545 lines of enforcement logic in `scripts/check-agent-docs.mjs` + `scripts/agent-docs/*.mjs`, against AGENTS.md §4 ("tests for every behavior change") | Seven AGENTS.md §5 rules now name this script as their enforcer, and its own comments record six fixed false-greens (`env-ignore.mjs:6`, `:11`, `check-agent-docs.mjs:63`, `:127`, `:213`, plus folded `run: >` scalars in `workflow.mjs:22`) — the next regression is silent again | Decide the harness: no precedent exists for testing `scripts/` (`doctor.mjs`, `pick-port.mjs` are untested), so this needs a small `node:test` runner over fixture repos, wired into `pnpm verify` as its own gate | Medium |
| `scripts/agent-docs/workflow.mjs:17,128` — `RUN_KEY` matches `run:` at any indentation (including under `with:`), and `readBlockScalar` does not advance the loop index, so block content is re-scanned as top-level lines | Non-executing text can satisfy "CI runs X". Verified with the real `run: pnpm verify:web` step deleted: both a heredoc containing `run: pnpm verify:web` and a `with:` input named `run` pass at exit 0 / 74 checks. Medium only because plain deletion of the job *is* caught | Anchor `run:` to step-level indentation (a `-` list item under `steps:`) and return the consumed line count from `readBlockScalar` so the loop skips past it | Medium |
| `scripts/agent-docs/env-ignore.mjs:36` — `isRepoIgnoreSource` validates the path *shape*, not that the `.gitignore` is tracked, while every message says "repo-tracked" | Verified both directions with an untracked `services/api/.gitignore` containing `.env.*`: false failure (`services/api/.env.example remains trackable — actual ignored`), and, with the root env section deleted, a false pass that is green locally and broken in a fresh clone | Confirm the matching source with `git ls-files --error-unmatch <source>`, or drop "repo-tracked" from the wording | Medium |
| `scripts/agent-docs/workflow.mjs:173` (`checkGateClaims`) — the package.json and CI-claims assertions are presence-only, so a neutered gate still satisfies them | A job disabled with `if: false` still satisfies "declares job X" / "runs X", and `"verify": "pnpm check:agent-docs && pnpm verify:api \|\| true && pnpm verify:web"` still satisfies every composition assertion — both verified at exit 0 / 74 checks. Needs deliberate neutering rather than deletion | Reject `if: false` (and equivalent always-false conditions) on the asserted jobs, and reject short-circuit operators (`\|\|`, `;`, `& `) inside the verify chains | Medium |
| `.github/workflows/ci.yml:4-5` — the header comment holds the only verbatim copy of the verify chain, and `scripts/agent-docs/workflow.mjs` strips comments before parsing by design | `docs/verification.md` makes `package.json` the single source of truth for the literal chain, so this last hand-maintained copy is permanently invisible to the guard and has already needed a hand edit once | Drop the `=` expansion from the comment and point at `package.json` instead | Low |
| The API contract check covers routes only; request/response *shapes* and the hand-written mirrors of the Pydantic models in `packages/shared/src/types.ts` are still hand-synced | Renaming or retyping a response field passes every gate — `docs/api/openapi.json` updates, the route set is unchanged, and the frontend keeps reading the old field as `undefined`. This is the half of "`api-client.ts` hand-synced to FastAPI" that the contract workflow did not close | Generate the shared TS types from `docs/api/openapi.json` (`openapi-typescript` emits types only, no client), or assert the schema of each client-consumed operation against `packages/shared` | Medium |

## Resolved

| Description | Resolution |
|---|---|
| `api-client.ts` hand-synced to FastAPI (route drift only) | Added deterministic OpenAPI workflow: `docs/api/openapi.json`, `pnpm contract:export`, `pnpm contract:check`, backend freshness coverage in `test_openapi_contract.py`, and frontend route drift coverage in `api-contract.test.ts`. Full codegen remains a future option only if this lightweight check proves insufficient. **Payload/type drift is not covered** — see the open row on `packages/shared/src/types.ts` |
| Byte-exact OpenAPI comparison against floating Python dependencies | Added `services/api/requirements.lock`, a complete Python 3.12 resolution installed by setup and CI. Intentional dependency refreshes now update the lock and `docs/api/openapi.json` together, so routine verification does not absorb upstream schema churn. |
| Rich metadata (checksums/EXIF/PDF) unavailable for already-stored files | `GET /files-by-key/detail` recomputes `FileMetadataDetail` on demand from the object bytes; `FileMetadataPanel` mounted in the Files preview dialog behind a lazy "Detailed metadata" disclosure |
| Blocking boto3 in `async def` handlers froze the single event loop | B2 handlers are sync `def` (Starlette threadpool); upload offloads via `run_in_threadpool` |
| Full-bucket scan on every list/stats/activity request, uncached | Short-TTL cache in `repo/b2_client._list_all_objects`, invalidated on upload/delete |
| No CI — quality gates ran only when a human remembered | `.github/workflows/ci.yml` runs all three `pnpm verify` gates — `check:agent-docs`, `verify:api`, `verify:web` — as parallel jobs on PR and push to `main` |
| README called AGENTS.md a "~100 line" entry point and concurrent `pnpm verify` shared Next.js's build lock | Replaced the stale size claims with bounded wording; the workflow supports one verification per worktree, documents the narrow `.next/lock` recovery, pre-commit use, timing, and separate E2E prerequisites |
| SVG stored-XSS; declared MIME trusted; unused `python-magic` dep | Dropped SVG from allow-list; added magic-byte signature check; removed dead `python-magic` |
| No rate limiting → DoS + B2 cost amplification | Per-IP fixed-window limiter (`runtime/ratelimit.py`), read/write budgets |
| Counter persistence lived in the service layer (layering violation) | Moved file I/O to `repo/counter.py` behind `get/increment_download_count` |
| CORS `allow_credentials=True` with no auth + regex escape hatch | Default `allow_credentials=False`; empty origins filtered |
| No security headers on API responses | `X-Content-Type-Options: nosniff` + `Referrer-Policy: no-referrer` on every response |
| Key-addressed ops could target any bucket object | Opt-in `ALLOWED_KEY_PREFIX` confinement (off by default, preserves arbitrary-key routes) |
| Redundant triple-scan + double sort per dashboard mount | TTL cache + single-flight collapse the concurrent empty-prefix scans; dropped the repo-layer sort so `get_files` owns newest-first ordering once |
| Unguarded `int(content-length)`; public `/docs`; uncached `/health` B2 call | Content-Length parse guarded; `ENABLE_DOCS` toggle; connectivity cached ~5s |
| Upload validation sad-paths (413/415) + sanitizer untested | `tests/test_upload_validation.py` covers the rejection matrix, signature, `uploads_total` |
| FastAPI `/docs` & `/redoc` undocumented | Documented in README; `ENABLE_DOCS` toggle added |
| `NEXT_PUBLIC_API_URL` missing from `.env.example` | Added with guidance |
| `get_upload_stats()` / `list_files()` object listing capped at 1000 | Shared `_list_all_objects()` paginator follows `ContinuationToken` |
| `datetime.utcnow()` deprecated in Python 3.12+ | Replaced with `datetime.now(UTC)` |
| S3 client recreated on every API call | Cached module-level singleton via `lru_cache` |
| `record_upload()` never called | Called from `runtime/upload.py` after upload |
| Metrics counters not thread-safe | Guarded by `threading.Lock` |
| `_humanize_bytes` duplicated in Python | Extracted to `app/types/formatting.py` |
| `humanizeBytes` / `formatDate` duplicated in TypeScript | Extracted to `lib/utils.ts` (tested) |
| Custom `FileNotFoundError` shadowed the built-in | Renamed to `FileNotFoundServiceError` |
| Dropzone accepted any file type client-side | `accept` allow-list mirroring backend `ALLOWED_TYPES` (tested for drift) |
| No test harness for feature specs | pytest suite across upload, files, activity, errors, validation, rate limit, pagination |

## 2026-11-04 — verify
- New batch dialog — Name input, Model card, version counts and Output format run past the dialog's right edge → cut-off text for first-time users (.local/verify/A-r3/15-cta-after-click.png)
- Photo Library — thumbnail tiles show as flat grey boxes for ~1–7s while images load (gate: over-claimed friction) → loading state not clearly distinguishable from broken (.local/verify/A-r3/17-photos-t1_4s.png)
- Photo Library — a sepia 3-channel historical scan is tagged "was color" → label may confuse archivists who know it is a B&W scan (.local/verify/A-r3/05-photo-library.png)
- Bucket Explorer — "Showing the 100 most recent of N objects", no load-more; top folder count reads "100 files" though it holds more → older originals unreachable, folder count reflects loaded items not totals (.local/verify/C-r3/08-bucket-explorer.png)
- Batch page — status badge reads "Queued" during model download/load → badge says waiting while work happens (stage line compensates) (.local/verify/B-r3/06b-batch-download-t8s.png)
- Batch page after Cancel — "Re-run 3 unfinished photos" changes to "Re-run 2" ~1s later as the in-flight photo finishes → count shifts after the user reads it (.local/verify/B-r3/11-cancel-settled.png)
- Bulk Ingest — rows being uploaded render very faint while a stale rejected .txt row stays full contrast → in-progress rows hard to read (.local/verify/B-r3/03-upload-in-progress.png)
- Batch page (paper model) — DDColor paper leaves some photos near-gray (Eiffel sat 0.019, Curie 0.076) with a cyan edge fringe → checkpoint variance; copy already says results vary (.local/verify/C-r3/06-library-after.png)

## 2026-11-05: verify
- New batch dialog: "Choose photos" is selected but helper reads "Default: every ingested original that no batch has colorized yet" → helper text contradicts the selected option (A/v4-07-new-batch-dialog.png)
- Dashboard: filled primary button is "Batches"; "Ingest photos" (first step) is secondary → emphasis on the later step (A/v4-01-home-first-load.png)
- Batch detail finishing: badge stays "Running" and Manifest CSV/Delete disabled 1-2s after all photos done while the manifest is written → looks briefly stuck, disabled buttons unexplained (A/v4-09-all-done-still-running.png)
- Batch detail breadcrumb: shows raw id "B 20261105 150256 48582d" → should show the batch name (A/v4-18-batch-settled.png)
- Bucket Explorer: sidebar view lists only 100 most recent objects; batch-focused view hides originals by default → outputs not shown beside originals by default (A/v4-19-explorer-via-link.png)
- Bucket Explorer batch view: "Also show originals" lists all 47 originals in grayscale/, not this batch's 4 → batch originals mixed with others (C/v4-07b-bucket-originals.png)
- Bucket Explorer batch view: banner says "colorized outputs, comparisons and manifest" on a batch with comparisons off → copy does not match batch settings (C/v4-08a-bucket-focus.png)
- Bucket Explorer batch view: subtitle "Browse and manage your most recent uploads" vs header "Files for this batch" → inconsistent copy (C/v4-07a-bucket-focus.png)
- Batch detail: progress bar only advances per finished photo, stays at 0 for ~10s through model load and photo 1 → looks stalled on the bar alone (B/v4-06-batch-midwait-later.png)
- Batch detail model load: badge reads "Queued" while stage says model is loading → badge contradicts stage (B/v3-05-batch-midwait-early.png)
- Batch detail cold download: placeholder bar pulses at 35% then the real bar starts at 0% → bar appears to move backwards (B/r4-05-mid-download.png)
- Bulk Ingest: "1 file need attention." → grammar, should be "needs" (B/v2-02-upload-bad-file.png)
- Bulk Ingest upload: no per-byte progress, only file-count stage → large scans would look stalled (B/v2-03-upload-in-progress.png)
- Bulk Ingest after upload: "Colorize these N photos" sits at the fold, partly clipped → primary next step easy to miss (A/v3-06-upload-complete.png)
- Batch detail side-by-side: opening a comparison leaves the row's cards uneven with large gaps → layout unbalanced (B/v3-11-side-by-side.png)
- Batches list: default name "DDColor artistic, 2026-11-05" repeats across rows → rows indistinguishable by name (A/v3-14-batches-list-after.png)
- Photo Library: tile leads with the latest (near-grayscale-flagged) paper version without any warning → library shows the weaker output unflagged (C/v3-06-library.png)
- Any page at 127.0.0.1:3000: "Can't reach the API" though API is up; dev CORS allows only localhost → misleading error for the 127.0.0.1 origin (A/v2-00-loopback-origin.png)

## 2026-11-05 — verify
- Dashboard `/`: "Batches" is the filled primary header button while "Ingest photos" (the real first step) is outline-styled → primary-action hierarchy points away from the first step (.local/verify/A-1105r2/10-landing.png)
- Dashboard on `http://127.0.0.1:3000`: "Can't reach the API ... Retry" banner although the API is up; API CORS only allows the `localhost` origin → misleading error with a Retry that cannot succeed; allow both loopback origins or name the origin problem (.local/verify/A-1105/01-landing.png)
- Batch detail for an unknown id: "Batch not found" with only a "Retry" primary action → Retry cannot help; make "Back to batches" the primary action (.local/verify/B-1105/01-bad-batch-id.png)
- Batch from "Colorize again with another model": auto-name "DDColor artistic, <date> (DDColor ModelScope)" keeps the parent model name → title leads with the wrong model; derive the suggested name from the newly chosen model (.local/verify/C-1105r2/06-batch-final.png)
- New batch dialog: helper text "Default: every ingested original that no batch has colorized yet." shown while "Choose photos" is selected → helper describes the unselected option (.local/verify/A-1105r1/16-new-batch-dialog.png)
- Bulk Ingest after upload: colorization needs one manual hand-off (button, dialog, Create batch) and the intro copy points to Photo Library/Batches rather than the in-page button → mention the post-upload action in the intro copy (.local/verify/A-1105r2/15-upload-complete.png)
