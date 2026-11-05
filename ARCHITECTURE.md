<!-- last_verified: 2026-11-04 -->
# Architecture

## Components

<!-- gen:begin arch-components -->
A batch photo colorization pipeline that bulk-ingests black-and-white scans to Backblaze B2, runs DDColor locally to produce full-color reconstructions at original resolution, and writes colorized outputs, side-by-side comparisons and a per-run manifest CSV back to B2 next to the untouched originals, so archives keep provenance and editorial teams can serve results through presigned URLs.

- **apps/web/** — Next.js 16, React 19, Tailwind v4, shadcn/ui, TanStack Query, Recharts
  - Batches (`/batches`) — create, edit, delete and run colorization batches with a per-run manifest
  - Photo Library (`/photos`) — grayscale originals with before/after views of every colorized version
  - Bulk Ingest (`/upload`) — drag-and-drop many scans straight to the grayscale prefix by presigned PUT
  - Dashboard (`/`) — photos ingested and colorized, derived bytes and the write-amplification ratio
  - Bucket Explorer (`/files`) — browse, preview, download and delete any object in the bucket
  - Settings (`/settings`) — theme plus labelled demo preference fields
- **services/api/** — FastAPI, Python 3.12+, boto3, Pydantic v2, Pillow, DDColor (PyTorch, optional ML extra)
  - REST API for every operation the frontend consumes, exported to `docs/api/openapi.json`
  - Backblaze B2 (S3-compatible API) access isolated in the `repo/` layer
  - Colorization — DDColor runs locally (CUDA, Apple MPS or CPU) and keeps the original resolution
  - Structured JSON logging with request tracing, plus `/health` and Prometheus `/metrics`
- **packages/shared/** — TypeScript types generated from the API contract by `pnpm gen:api`, consumed by `apps/web/` as a workspace dependency (pnpm workspaces)
<!-- gen:end arch-components -->

## Backend Layering

The API follows a strict layered architecture:

```
types/     Pydantic models (batches, photos, files, upload) — no logic
  |
config/    Settings (pydantic-settings) — depends only on types
  |
repo/      Adapters: boto3 B2 access, batch record store, Pillow imaging,
  |        comparison composite, manifest CSV, and the DDColor engine
service/   Business logic: key layout, batch lifecycle, the colorize runner,
  |        Photo Library + dashboard aggregates, upload validation
runtime/   FastAPI routes — calls service, never repo directly
```

### Layering Rules

1. Dependencies flow downward only: `types` -> `config` -> `repo` -> `service` -> `runtime`
2. No backward imports (e.g., service must not import from runtime)
3. `boto3` only allowed in `repo/` layer
4. `torch`, DDColor and their closure (`torchvision`, `timm`, `cv2`, `huggingface_hub`) only in `repo/ddcolor.py`, imported lazily inside functions
5. All boundary data uses Pydantic models (no raw dicts across layers)
6. Authored Python files under `services/api/app/` stay under 300 lines

### Directory Structure

<!-- gen:begin arch-directory -->
```
services/api/
  main.py                  App entrypoint, middleware, router registration
  app/
    types/                 Pydantic models, and the response-model base
    config/                Settings loaded from environment
    repo/                  B2 S3 client (data access layer)
    service/               Business logic
    runtime/               FastAPI route handlers
  scripts/                 Operational scripts (OpenAPI export, bucket CORS)
  tests/                   pytest tests (structural + integration)
```
<!-- gen:end arch-directory -->

The sample's own modules inside that tree:

```
app/types/batches.py, photos.py          Batch, BatchRecord, Photo, ColorizationStats, enums
app/repo/b2_io.py                        put_object / list_objects_v2 / delete_objects (tagged client)
app/repo/batch_store.py                  batch records as JSON objects, ETag-keyed cache, mutate()
app/repo/ddcolor.py                      lazy DDColor engine, device auto-detect, one resident model
app/repo/imaging.py, comparison.py       Pillow decode/encode/saturation, side-by-side composite
app/repo/manifest.py                     per-batch manifest CSV writer
app/service/keys.py                      the B2 key layout, declared once
app/service/batches.py                   create / read / edit / delete / run
app/service/colorize_runner.py           background worker thread + restart recovery
app/service/photos.py                    Photo Library pages and dashboard stats
app/runtime/batches.py, photos.py        routers
scripts/install_ml.sh                    `pnpm setup:ml` (and the Railway build)
scripts/seed_demo.py                     `pnpm seed:demo` public-domain demo photos
```

## B2 Key Layout

Everything the app writes lives under one prefix (`COLORIZATION_PREFIX`, default
`colorization/`), declared once in `services/api/app/service/keys.py`:

```
colorization/grayscale/<filename>                         ingested original (never modified)
colorization/colorized/<batch_id>/<stem>.<jpg|png|webp>   colorized output, original resolution
colorization/comparisons/<batch_id>/<stem>.jpg            optional side-by-side comparison
colorization/manifests/<batch_id>.csv                     per-run manifest
colorization/batches/<batch_id>.json                      the Batch record (config, status, items)
colorization/flags/was-color/<filename>                   marker: the original was a colour image
```

Outputs are keyed by batch, so re-running the same originals with another model
keeps both versions. Two originals with the same stem in one batch get `-2`, `-3`
suffixes rather than overwriting each other.

## Boundary Invariants

- **No external SDK leakage**: `boto3` is only imported in `app/repo/`, and the ML stack only in `app/repo/ddcolor.py`. Both are asserted by `tests/test_structure.py`.
- **The core runs without the ML stack**: `ddcolor.ml_available()` checks importability with `importlib.util.find_spec` (no import), so `pnpm verify`, CI and every non-colorizing route work in the core venv. Running a batch without it returns 503 with the install command.
- **No raw dicts at boundaries**: All data crossing layer boundaries uses typed Pydantic models.
- **Shared state is module-local and locked**: the listing cache, connectivity cache, download counter, rate-limit and metrics state (kit), plus the batch record cache in `repo/batch_store.py` and the single resident DDColor model in `repo/ddcolor.py`. All writes to a batch record go through `batch_store.mutate()` under one lock, so a rename made while a batch runs is not overwritten by the runner's next progress write.
- **Background threads**: the kit's listing-cache refresher, the colorize runner (`service/colorize_runner.py`, one daemon thread fed by a FIFO queue, one batch at a time), and a one-shot startup recovery thread that marks batches a previous process left `queued`/`running` as `interrupted`.
- **Validated inputs**: All HTTP inputs validated by FastAPI/Pydantic. Batch ids must match `b-YYYYMMDD-HHMMSS-<hex>`; photo keys must be direct children of `grayscale/`. Bucket Explorer by-key operations are confined to `ALLOWED_KEY_PREFIX`, which defaults to `colorization/` (set it empty to allow any key).

## Deployment

- **Local dev** (the primary use) — `pnpm dev` runs both services via `concurrently`
  - Web: `localhost:3000`
  - API: `localhost:8000`, with the DDColor stack from `pnpm setup:ml`
- **Railway** — two services from the same repository: `web` builds from the
  repository root because it consumes `packages/shared`; `api` builds from
  `services/api`. Each service's versioned config sits at its own root,
  `railway.json` and `services/api/railway.json`. The API build installs
  `requirements.lock` and then the ML stack through `scripts/install_ml.sh` (CPU
  PyTorch wheels on Linux; set `TORCH_INDEX_URL` for a CUDA host). Weights
  download on the first batch after each deploy unless `HF_HOME` points at a
  volume. The human-approved staging/production contract lives in
  [infra/railway/README.md](infra/railway/README.md).
- **No Vercel target**: PyTorch inference with 220 to 900 MB checkpoints does
  not fit a serverless function, so the sample ships no Vercel configuration.

External provisioning and deployment remain explicit user-approved actions.

## Data Stores

<!-- gen:begin arch-data-stores -->
- **Backblaze B2 (S3-compatible API)** — the only data store; there is no application database
  - Every object this app writes lives under the `colorization/` key prefix of one bucket
  - Listing, per-key metadata and presigned URLs all come from the S3 surface below
  - The primary entity is `Batch`; one batch is one object
<!-- gen:end arch-data-stores -->

## External Services

<!-- gen:begin arch-external-services -->
- **Backblaze B2 (S3-compatible API)** — reached only through `services/api/app/repo/`, using:
  - `presigned PUT` — the browser bulk-ingests originals straight to the grayscale prefix
  - `head_object` — verify an ingested upload, read per-key size, and the /health connectivity probe
  - `get_object` — read an original for inference and read batch records
  - `put_object` — write colorized outputs, comparison images, manifest CSVs and batch records
  - `list_objects_v2` — the Photo Library, batch list, dashboard aggregates and the full-bucket explorer
  - `presigned GET` — serve originals, colorized images, comparisons and manifests to viewers and CMS import jobs
  - `delete_objects` — remove a batch's derived objects while keeping the originals, and Bucket Explorer deletes
<!-- gen:end arch-external-services -->

- **Hugging Face Hub** — public `piddnad/ddcolor_*` checkpoints, downloaded by
  `huggingface_hub` inside `repo/ddcolor.py` on first use and cached under
  `HF_HOME`. No token. The resolved revision sha is recorded per batch as
  `model_version` and in every manifest row.

## Trust Boundaries

See [docs/SECURITY.md](docs/SECURITY.md) for full security documentation.

- **Frontend -> API** — CORS-restricted to configured origins (GET, POST, PATCH, DELETE). `CORSMiddleware` is registered LAST in `main.py` (outermost) so it wraps **every** response, including uncaught-exception 500s. See [docs/RELIABILITY.md](docs/RELIABILITY.md#error-handling). A per-IP rate-limit middleware sits inner to CORS; see [docs/SECURITY.md](docs/SECURITY.md#rate-limiting).
- **API -> B2** — authenticated via application keys, signature v4, custom user agent `b2ai-ddcolor-photo-colorization` on every S3 client
- **Client -> B2** — presigned PUT for ingest (15 min, size and type signed in); presigned GET for gallery views (1 hour, inline) and downloads (10 min, attachment)

## Data Flows

- **Ingest**: Browser -> `POST /upload/presign` (image types only; key minted under `colorization/grayscale/`) -> Browser PUTs bytes **directly to B2** -> `POST /upload/verify` (HEAD + magic-byte sniff, then a saturation check that writes a `flags/was-color/` marker for colour images) -> response with `was_color`
- **Create batch**: `POST /batches` -> resolve sources against a `list_objects_v2` of `grayscale/` (or "all not yet colorized" from the batch records) -> `put_object` the record -> queue it when `run_now`
- **Run**: worker -> per photo `get_object` original -> decode + desaturate -> DDColor (`ab` at 256/512, recombined with the original `L`) -> `put_object` colorized -> optional comparison `put_object` -> record update -> after the last photo, manifest CSV `put_object` -> final status `done` / `partial` / `failed`
- **Photo Library**: `GET /photos` -> `list_objects_v2` of `grayscale/` and `flags/was-color/` + batch records -> presigned GETs for the original and latest version
- **Dashboard**: `GET /batches/stats` -> one `list_objects_v2` of `colorization/` summed by sub-prefix + batch records
- **Delete batch**: `DELETE /batches/{id}` -> list the batch's `colorized/` and `comparisons/` prefixes -> `delete_objects` with the manifest and record; originals untouched
- **Bucket Explorer** (kit): `GET /files` lists the whole bucket from a shared cached scan; by-key preview, download, detail and delete go through `head_object`, presign and `delete_object`

## Observability

- Structured JSON logging on all requests with `request_id`; the runner logs the model version and device per batch and a warning per failed photo
- Request timing middleware (also the catch-all that converts uncaught exceptions to a typed JSON 500)
- `/metrics` endpoint (Prometheus format: request count, latency, upload count)
- `/health` endpoint (B2 connectivity check)

## API Contract

<!-- gen:begin arch-api-contract -->
- Checked-in OpenAPI artifact: `docs/api/openapi.json`
- Export / check: `pnpm contract:export` / `pnpm contract:check`
- Generate the client seam from it: `pnpm gen:api` (drift gate: `pnpm gen:check`)
- FastAPI freshness test: `services/api/tests/test_openapi_contract.py`
- Frontend route drift test: `apps/web/src/lib/api-contract.test.ts`

The FastAPI routers and Pydantic models are the single source of truth. The
frontend's `API_CLIENT_ROUTES` registry, the `qk` query-key factory and the
shared TypeScript types are **generated** from the exported artifact by
`pnpm gen:api`, so the client cannot drift from the backend — there is no
hand-written copy left to disagree. The two contract tests are kept as a
belt-and-braces check that the generated files and the committed artifact are
still in step.

| Route | Returns | Generated client route |
| --- | --- | --- |
| `DELETE /batches/{batch_id}` | `DeleteBatchResponse` | `batchDelete` |
| `DELETE /files-by-key` | `DeleteFileResponse` | `fileByKeyDelete` |
| `DELETE /files/{key}` | `DeleteFileResponse` | `legacyFileDelete` |
| `GET /batches` | `Batch[]` | `batches` |
| `GET /batches/{batch_id}` | `BatchDetail` | `batch` |
| `GET /batches/{batch_id}/manifest/download` | `FileUrlResponse` | `batchManifestDownload` |
| `GET /batches/stats` | `ColorizationStats` | `batchStats` |
| `GET /files` | `FileMetadata[]` | `files` |
| `GET /files-by-key/detail` | `FileMetadataDetail` | `fileByKeyDetail` |
| `GET /files-by-key/download` | `FileUrlResponse` | `fileByKeyDownload` |
| `GET /files-by-key/metadata` | `FileMetadata` | `fileByKeyMetadata` |
| `GET /files-by-key/preview` | `FileUrlResponse` | `fileByKeyPreview` |
| `GET /files/{key}` | `FileMetadata` | `legacyFileMetadata` |
| `GET /files/{key}/download` | `FileUrlResponse` | `legacyFileDownload` |
| `GET /files/{key}/preview` | `FileUrlResponse` | `legacyFilePreview` |
| `GET /files/stats` | `UploadStats` | `fileStats` |
| `GET /files/stats/activity` | `DailyUploadCount[]` | `uploadActivity` |
| `GET /health` | `HealthStatus` | `health` |
| `GET /metrics` | — | _server-only_ |
| `GET /photos` | `PhotoPage` | `photos` |
| `GET /photos-by-key/detail` | `PhotoDetail` | `photoDetail` |
| `PATCH /batches/{batch_id}` | `Batch` | `batchUpdate` |
| `POST /batches` | — | `batchCreate` |
| `POST /batches/{batch_id}/cancel` | `Batch` | `batchCancel` |
| `POST /batches/{batch_id}/run` | `Batch` | `batchRun` |
| `POST /upload/presign` | `PresignUploadResponse` | `uploadPresign` |
| `POST /upload/verify` | `FileUploadResponse` | `uploadVerify` |
<!-- gen:end arch-api-contract -->

## Canonical Files

<!-- gen:begin arch-canonical-files -->
Hand-written — this is the file to edit:

- Layered API handler: `services/api/app/runtime/`
- Service orchestration: `services/api/app/service/`
- B2 data access (repo layer): `services/api/app/repo/b2_client.py`
- Pydantic models: `services/api/app/types/` (`base.py` carries the response-model config)
- Config (pydantic-settings): `services/api/app/config/settings.py`
- Structural tests: `services/api/tests/test_structure.py`
- OpenAPI exporter: `services/api/scripts/export_openapi.py`
- Frontend API client — error policy, transport, fallback: `apps/web/src/lib/api-client.ts`
- Frontend data layer — caching, invalidation, polling: `apps/web/src/lib/queries.ts`
- Shared type barrel: `packages/shared/src/types.ts`
- Generator policy: `scripts/gen/api-gen.config.json`
- Sample manifest behind the generated docs: `docs/exec-plans/sample.json`

Generated — **never hand-edit**; change the source and re-run the command:

- `docs/api/openapi.json` — `pnpm contract:export` (source: the routers and models)
- `packages/shared/src/generated/api-types.ts` — `pnpm gen:api`
- `apps/web/src/lib/generated/api-routes.ts` — `pnpm gen:api`
- `apps/web/src/lib/generated/query-keys.ts` — `pnpm gen:api`
- The marker-delimited regions of this file, `AGENTS.md`, `README.md` and the 1 `infra/` runbooks — `pnpm gen:docs`
<!-- gen:end arch-canonical-files -->

## Core Features

<!-- gen:begin arch-core-features -->
- [Batches](docs/features/batches.md) — create, edit, delete and run colorization batches with a per-run manifest
- [Colorization](docs/features/colorization.md) — DDColor runs locally (CUDA, Apple MPS or CPU) and keeps the original resolution
- [Photo Library](docs/features/photo-library.md) — grayscale originals with before/after views of every colorized version
- [Bulk Ingest](docs/features/file-upload.md) — drag-and-drop many scans straight to the grayscale prefix by presigned PUT
- [Dashboard](docs/features/dashboard.md) — photos ingested and colorized, derived bytes and the write-amplification ratio
- [Bucket Explorer](docs/features/file-browser.md) — browse, preview, download and delete any object in the bucket
- [Settings](docs/features/settings.md) — theme plus labelled demo preference fields
<!-- gen:end arch-core-features -->

## References

<!-- gen:begin arch-references -->
- [docs/SECURITY.md](docs/SECURITY.md) — security principles and implementation
- [docs/RELIABILITY.md](docs/RELIABILITY.md) — reliability expectations
- [AGENTS.md](AGENTS.md) — architectural invariants and agent instructions
- [infra/railway/README.md](infra/railway/README.md) — Railway delivery contract
<!-- gen:end arch-references -->
