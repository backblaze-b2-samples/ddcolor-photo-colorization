# Build plan: `ddcolor-photo-colorization`

Scaffolded from the `backblaze-b2-samples/vibe-coding-starter-kit` repository at
commit `5301214225ad2edc1520d57e400a5b21ecb18a32`. The starter kit is the ceiling:
strip what this app does not need rather than rebuild.

## 1. Purpose

A batch **black-and-white photo colorization pipeline** for digital archives,
newspapers and historical societies. Grayscale or desaturated scans (prints,
digitized negatives, legacy JPEG archives) are bulk-ingested to a Backblaze B2
`grayscale/` prefix; **DDColor runs locally** on each photo and produces a
full-color reconstruction at the original resolution; colorized outputs, optional
side-by-side comparison images and a per-run manifest CSV are written back to B2
next to the untouched originals, so provenance is preserved and editorial teams or
a CMS can pull results through presigned URLs. It is for archive engineers and
digital-collections teams who want a self-hosted, reproducible colorization
workflow. The star of the sample is the **write-amplification** story (every
ingested photo yields a colorized counterpart, optionally a comparison image, and
a manifest row, so stored bytes grow with each run and each model variant) with
**B2 as the sole storage layer**, accessed through the S3-compatible API with a
custom user agent and the standard `B2_*` env vars, and **no second API key**
(colorization is on-device open source software).

## 2. Architecture delta from vibe-coding-starter-kit

Backend layering (`types -> config -> repo -> service -> runtime`), the generated
API and doc seams, the shadcn UI kit and every mechanical gate (`pnpm verify`,
`check:agent-docs`, `gen:check`) are kept and respected.

**KEEP (as-is)**
- UI kit `apps/web/src/components/ui/`, design tokens in `globals.css`, the
  `/design` page, layout shell (sidebar, header, command palette, health banner).
- **Bucket Explorer**: `/files`, `apps/web/src/app/files/`, `components/files/`,
  the full-bucket `list_objects_v2` listing and its `/files*` and
  `/files-by-key/*` endpoints. Non-negotiable keep: the bucket explorer is never
  removable. It also backs generic file detail (the kit's metadata extraction).
- **Upload** route `/upload`, `components/upload/` and the presigned-PUT flow,
  repurposed as **Bulk Ingest** (see ADD) rather than replaced.
- **Settings** (`/settings`, `settings-form.tsx`, danger zone).
- Backend `repo/b2_client.py`, `repo/b2_object.py`, `repo/b2_upload.py`,
  `repo/list_cache.py`, `repo/counter.py`, `runtime/health.py`,
  `runtime/metrics.py`, `runtime/ratelimit.py`, the file and upload services.
- Railway infra, generators (`gen:docs`, `gen:api`, `contract:export`), CI, agent
  doc shims (`AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, copilot instructions).

**TRIM (remove from starter)**
- **Vercel deployment**: remove root `vercel.json`, `apps/web/vercel.json`,
  `services/api/vercel.json`, `services/api/index.py` and its
  `test_vercel_entrypoint.py`, `infra/vercel/` and the Vercel one-click button.
  Rationale: DDColor runs PyTorch inference with a ConvNeXt backbone and model
  weights in the hundreds of MB, which does not fit or finish inside a serverless
  function, so a Vercel button would promise a deploy that cannot colorize.
  `deployment_targets` becomes `["railway"]`; the primary intended use is local
  `pnpm dev`, and Railway is the hosted path (CPU works, a GPU is faster).
- **Dashboard** default cards, upload chart and recent-uploads table: rewritten
  (see ADD), not kept verbatim.
- `docs/features/metadata-extraction.md`: delete as a standalone feature doc
  (EXIF/PDF focus is off-theme). The generic detail endpoint stays and is
  documented inside the Bucket Explorer feature doc.
- Upload accept-list entries for non-image types (PDF, audio, video, archives):
  Bulk Ingest accepts images only (JPEG, PNG, TIFF, WebP, BMP).

**ADD (new for this app)**
- **Batches** (`/batches`, `/batches/[id]`): the primary entity's screens. A batch
  is one colorization run over a chosen set of grayscale originals with a fixed
  model configuration; it owns its colorized outputs, comparisons and manifest.
  List view with status, counts and bytes; detail view with per-photo progress,
  before/after gallery, manifest download, edit, delete and run/re-run actions.
- **Photo Library** (`/photos`): the **sample-specific asset explorer**, scoped to
  this app's `colorization/` prefix (distinct from the kept full-bucket explorer).
  Grid of grayscale originals; each card shows its latest colorized version; a
  detail sheet shows a before/after slider and every colorized version across
  batches (model, timestamp, size) with presigned download links.
- **Bulk Ingest** (rewritten `/upload`): drag-and-drop many images, uploaded by
  presigned PUT straight into `colorization/grayscale/`. Each upload is checked
  for color saturation after verify; already-color images are accepted (they are
  desaturated to L before inference) and flagged `was_color` in the listing.
- Backend `repo/ddcolor.py`: the **only** place `torch` and DDColor are imported,
  and **lazily**, so the core API and `pnpm verify` run without ML deps. Loads the
  selected DDColor checkpoint from the Hugging Face Hub once and caches it per
  model id. Inference follows DDColor's own pipeline: convert to Lab, predict the
  `ab` channels at the model input size, resize `ab` back to the original
  resolution, and recombine with the original `L` channel, so the output matches
  the source dimensions exactly.
- Backend `repo/comparison.py`: Pillow side-by-side composite (original | color)
  with a small caption strip (model id). Light dep, core.
- Backend `repo/manifest.py`: CSV writer for the per-batch manifest.
- `types/batches.py`, `types/photos.py`, `service/batches.py`,
  `service/photos.py`, `service/colorize_runner.py` (background worker),
  `runtime/batches.py`, `runtime/photos.py`.
- **Runner**: one background worker thread with a FIFO queue; one batch runs at a
  time (the model is memory-heavy). Per photo: `get_object` original -> DDColor ->
  `put_object` colorized -> optional comparison `put_object` -> update batch
  record. A failure on one photo marks that item `failed` with its error and the
  batch continues; the batch ends `done` or `partial`. The manifest CSV is written
  after the last item. Status is persisted in the batch record so a restart shows
  an interrupted batch as `interrupted` (re-runnable), never stuck `running`.
- Rewritten **Dashboard**: photos ingested, photos colorized, batches run,
  grayscale bytes vs derived bytes (colorized + comparisons + manifests), and the
  **write-amplification ratio** as the headline metric, plus recent batches.
- `services/api/requirements-ml.txt` (optional ML deps, see section 4) and
  `scripts/seed_demo.py` (fetches a handful of public-domain historical photos,
  each with its source URL and license recorded in the script, and ingests them
  through the S3 API). No binary assets are committed.

**B2 key layout** (everything under one app prefix, `colorization/`):
```
colorization/grayscale/<filename>                       ingested original (never modified)
colorization/colorized/<batch_id>/<stem>.<jpg|png|webp> colorized output at original resolution
colorization/comparisons/<batch_id>/<stem>.jpg          optional side-by-side comparison
colorization/manifests/<batch_id>.csv                   per-run manifest
colorization/batches/<batch_id>.json                    the Batch record (config, status, items)
```
`ALLOWED_KEY_PREFIX` = `colorization/`. Colorized outputs are keyed by batch so
re-running with another model keeps both versions (provenance, and more stored
bytes by design).

**Manifest CSV columns**: `original_key, colorized_key, comparison_key,
model_id, model_version, input_size, output_format, width, height,
original_bytes, colorized_bytes, duration_ms, status, error,
processed_at` (ISO 8601 UTC). `model_version` is `<model_id>@<HF revision sha>`.

**Tension noted**: none with the bucket explorer; it stays as the full-bucket view
and the Photo Library is the scoped view.

## 3. B2 surface (S3-compatible only, no b2-native)

All operations go through boto3 in `repo/`, every client built by the kit's
`b2_client.py` with the custom user agent. No b2-native API anywhere.

| Operation | Why |
|---|---|
| presigned PUT | browser bulk-ingests originals straight to `grayscale/` |
| head_object | verify an ingested upload; per-key size; `/health` probe |
| get_object | read an original for inference; read batch records |
| put_object | write colorized outputs, comparisons, manifests, batch records |
| list_objects_v2 | Photo Library, batch list, dashboard aggregates, full-bucket explorer |
| presigned GET | serve originals, colorized images, comparisons and manifests to viewers and CMS jobs |
| delete_object / delete_objects | delete a batch's derived objects; Bucket Explorer delete |

**API endpoints (recorded once here; routers and Pydantic models implement it,
`pnpm contract:export` + `pnpm gen:api` derive the web seam):**

| Path | Method | Request model | Response model |
|---|---|---|---|
| `/batches` | GET (`?limit`) | none | `list[Batch]` |
| `/batches` | POST | `CreateBatchRequest` | `Batch` |
| `/batches/stats` | GET | none | `ColorizationStats` |
| `/batches/{batch_id}` | GET | none | `BatchDetail` |
| `/batches/{batch_id}` | PATCH | `UpdateBatchRequest` | `Batch` |
| `/batches/{batch_id}` | DELETE | none | `DeleteBatchResponse` |
| `/batches/{batch_id}/run` | POST | none | `Batch` (status `queued` or `running`) |
| `/batches/{batch_id}/manifest/download` | GET | none | `FileUrlResponse` (reused) |
| `/photos` | GET (`?limit`, `?cursor`) | none | `PhotoPage` |
| `/photos-by-key/detail` | GET (`?key`) | none | `PhotoDetail` |

Kept unchanged: `/files*`, `/files-by-key/*`, `/files/stats*`, `/upload/presign`,
`/upload/verify` (presign now targets the `colorization/grayscale/` prefix),
`/health`, `/metrics`.

**Pydantic models**:
- `ModelId` enum: `ddcolor_modelscope`, `ddcolor_paper`, `ddcolor_artistic`,
  `ddcolor_paper_tiny`. `InputSize` enum: `256`, `512`. `OutputFormat` enum:
  `jpeg`, `png`, `webp`. `BatchStatus` enum: `draft`, `queued`, `running`,
  `done`, `partial`, `failed`, `interrupted`. `ItemStatus` enum: `pending`,
  `running`, `done`, `failed`.
- `Batch`: batch_id, name, description|None, model_id, input_size,
  output_format, make_comparisons, status, photo_count, done_count,
  failed_count, original_bytes, derived_bytes, manifest_key|None, created_at,
  updated_at, started_at|None, finished_at|None.
- `BatchItem`: original_key, colorized_key|None, comparison_key|None, status,
  error|None, width|None, height|None, duration_ms|None, plus presigned
  `original_url`, `colorized_url|None`, `comparison_url|None` in detail.
- `BatchDetail`: `Batch` + `items: list[BatchItem]`.
- `CreateBatchRequest`: name, description?, source_keys (list of keys under
  `grayscale/`, or empty with `all_unprocessed=true`), all_unprocessed, model_id,
  input_size, output_format, make_comparisons, run_now.
- `UpdateBatchRequest`: name?, description?.
- `DeleteBatchResponse`: batch_id, deleted_objects. Deletes the batch's
  colorized outputs, comparisons, manifest and record; **never** the grayscale
  originals.
- `Photo`: key, filename, size, last_modified, was_color, colorized_versions
  count, latest presigned `original_url` and `colorized_url|None`.
- `PhotoPage`: items + next_cursor. `PhotoDetail`: `Photo` + every version
  (batch_id, model_id, colorized_key, size, processed_at, presigned URLs).
- `ColorizationStats`: photos_ingested, photos_colorized, batches_total,
  grayscale_bytes, derived_bytes, amplification_ratio, recent_batches.
- `primary_entity.schema` = `Batch`.

## 4. Key features

**External API provider: none.** Colorization with DDColor is the sample's whole
point and it is on-device open source software, so no external provider is used
and the feature is `deployment: local`. Cost per full demo run: **$0** (no
external API; B2 storage only). No provider key.

Per-feature deployment:
- **Colorization**: `deployment: local`. Engine: DDColor (`piddnad/DDColor`,
  Apache-2.0), installed from its GitHub repository pinned to a commit, weights
  from the public Hugging Face Hub repos `piddnad/ddcolor_*` (no token needed).
  Device: defaults to CPU and auto-detects a GPU at runtime, first available of
  **CUDA -> Apple MPS -> CPU**; override with `DDCOLOR_DEVICE=auto|cpu|cuda|mps`.
  ConvNeXt inference works on MPS; set `PYTORCH_ENABLE_MPS_FALLBACK=1` so any
  unsupported op falls back to CPU rather than failing. Heavy deps (`torch`,
  `torchvision`, `timm`, DDColor) live in **`services/api/requirements-ml.txt`**,
  are lazy-imported inside `repo/ddcolor.py`, and are **not** in the core
  `requirements.lock`, so `pnpm verify` and CI stay light. When ML deps are
  missing, `POST /batches/{id}/run` returns a clear 503 with the install command
  and the UI shows it. Demo default `ddcolor_paper_tiny` at input 512 keeps a CPU
  run short; `ddcolor_modelscope` is the quality option.
- **Comparisons and Manifest**: `deployment: local`, Pillow and the csv stdlib.
- **Batches, Photo Library, Bulk Ingest, Dashboard, Bucket Explorer, Settings**:
  no external deps.

Feature bullets (seed the README and `docs/features/*.md`): Batches, Colorization,
Photo Library, Bulk Ingest, Dashboard (write amplification), Bucket Explorer,
Settings.

**Primary entity: `Batch`.** All lifecycle verbs are built in the UI;
`omitted_ui_verbs` = [].
- **create**: "New batch" dialog/page on `/batches` (form UX below), also
  reachable from Photo Library multi-select ("Colorize selected").
- **read**: batch list and batch detail with per-item progress and gallery.
- **edit**: rename and edit description from the detail page (configuration is
  immutable after creation because it defines what the outputs and manifest mean;
  to change the model, create a new batch).
- **delete**: delete a batch and its derived objects, with a confirm dialog that
  states originals are kept.
- **run**: "Run" on a draft, "Re-run" on a finished, partial, failed or
  interrupted batch (re-run overwrites that batch's own outputs and manifest).
  The detail page polls while `queued` or `running`.

**Form UX conventions** (in-repo exemplar:
`apps/web/src/components/settings/settings-form.tsx`):
- Selectors, never free text, for finite-value fields on both create and edit:
  `model_id` -> `Select` (with a one-line description per variant);
  `input_size` -> segmented control (256 / 512); `output_format` -> segmented
  control (JPEG / PNG / WebP); `make_comparisons` -> `Switch`; `run_now` ->
  `Switch`; source selection -> `RadioGroup` ("All not yet colorized" /
  "Choose photos") plus a checklist of Photo Library items for the latter.
- Create-form safe defaults shown as placeholder / `FormDescription` guidance
  only, never an autofill button: name e.g. "Archive box 1", model
  `ddcolor_paper_tiny` (fastest on CPU), input size 512, output JPEG,
  comparisons on, run now on, source "All not yet colorized".
- Edit form opens pre-filled with name and description only; the configuration
  fields are shown read-only.

**Demo data provenance** (for later screenshot and run steps): public-domain
historical photographs (for example Library of Congress items marked "no known
restrictions" or Wikimedia Commons public-domain files), favouring streets,
buildings, transport and landscapes; source URL and license recorded per image in
`scripts/seed_demo.py`.

## 5. Doc transforms

- **New** feature docs: `docs/features/batches.md`,
  `docs/features/colorization.md`, `docs/features/photo-library.md`.
- **Rewrite**: `docs/features/dashboard.md` (write amplification and colorization
  metrics), `docs/features/file-upload.md` (Bulk Ingest),
  `docs/features/file-browser.md` (Bucket Explorer, now also documenting the
  generic detail endpoint).
- **Keep**: `docs/features/settings.md`, `docs/features/_template.md`.
- **Delete**: `docs/features/metadata-extraction.md`.
- **Update by hand**: `PRODUCT.md`, `docs/SECURITY.md` (presigned URL expiry,
  originals never overwritten), `docs/RELIABILITY.md` (runner queue, restart
  behaviour), `docs/verification.md` and `docs/dev-workflows.md` (optional ML
  install: `pip install -r services/api/requirements-ml.txt`).
- `ARCHITECTURE.md`, `README.md`, `AGENTS.md`, `docs/app-workflows.md` and the
  Railway runbook mechanical regions are regenerated by `pnpm gen:docs` from the
  manifest; generated regions are not hand-edited.

**Declared identity: `docs/exec-plans/sample.json`** (authority: the kit's
`scripts/gen/sample.schema.json`), written before the docs are generated:
- `schema_version` 1
- `name` "DDColor Photo Colorization"
- `slug` "ddcolor-photo-colorization"
- `package_scope` "@ddcolor-photo-colorization"
- `purpose`: one sentence, see the file
- `tagline` "Colorize black-and-white photo archives with DDColor and keep every original and output in Backblaze B2."
- `primary_entity` { schema "Batch", singular "batch", plural "batches" }
- `features`: the seven in section 4
- `b2_surface`: section 3 operations with why
- `b2_key_prefix` "colorization/"
- `stack.web` "Next.js 16, React 19, Tailwind v4, shadcn/ui, TanStack Query, Recharts";
  `stack.api` "FastAPI, Python 3.12+, boto3, Pydantic v2, Pillow, DDColor (PyTorch, optional ML extra)";
  `stack.storage` "Backblaze B2 (S3-compatible API)"; `stack.package_manager` "pnpm workspaces"
- `deployment_targets` ["railway"]
- `env_vars`: `B2_APPLICATION_KEY_ID`, `B2_APPLICATION_KEY`, `B2_BUCKET_NAME`,
  `B2_REGION` (required); `B2_PUBLIC_URL_BASE`, `NEXT_PUBLIC_API_URL`,
  `DDCOLOR_DEVICE` (optional, auto|cpu|cuda|mps, default auto), `HF_HOME`
  (optional, model weight cache directory)
- `attribution_token` "b2ai-ddcolor-photo-colorization"
- `repo` { org "backblaze-b2-samples", name "ddcolor-photo-colorization" }
- `screenshots` [] (added once screenshots are captured)

## 6. Rename table

| From (`vibe-coding-starter-kit`) | To |
|---|---|
| Display name `Vibe Coding Starter Kit` | `DDColor Photo Colorization` |
| slug `vibe-coding-starter-kit` | `ddcolor-photo-colorization` |
| snake form `vibe_coding_starter_kit` (if any) | `ddcolor_photo_colorization` |
| package scope `@vibe-coding-starter-kit` (`/web`, `/shared`) | `@ddcolor-photo-colorization` |
| attribution token `b2ai-oss-start` (S3 `user_agent_extra` and every `utm_content`) | `b2ai-ddcolor-photo-colorization` |
| `APP_NAME` in `apps/web/src/lib/app-config.ts` | `DDColor Photo Colorization` |
| FastAPI `API_TITLE` (derived from `APP_NAME`) | `DDColor Photo Colorization` |
| `localStorage` namespace and CORS rule id (derived from slug) | `ddcolor-photo-colorization` |
| repo `org/name`, clone URL, deploy links | `backblaze-b2-samples/ddcolor-photo-colorization` |
| image tags, workflow slugs, Railway service names | `ddcolor-photo-colorization*` |
| Title-case prose in docs | `DDColor Photo Colorization` |

These derive from `sample.json` and `app-config.ts`; `pnpm gen:docs` rewrites the
generated regions and `pnpm gen:check` catches misses.

## 7. Verification expectation

Verification runs `pnpm run setup` then `pnpm verify` (core, credential-free, no
ML deps). The build adds unit tests for the manifest writer, comparison composite, key
layout, batch state transitions (including `interrupted` on restart) and the
503-without-ML path, and checks the three B2 standards (S3 API by default, custom user agent on
every client, `B2_*` names). Real colorization is exercised at run time with the
optional ML deps, not inside `verify`.
