<!-- last_verified: 2026-11-04 -->
# Feature: Batches

## Purpose
Group a set of grayscale originals with one fixed DDColor configuration into a run that owns its colorized outputs, comparisons and manifest, so every derived image is traceable to the settings that produced it.

## Used By
- UI: `/batches` (list + **New batch** dialog), `/batches/[id]` (progress, gallery, manifest, edit, delete, run/re-run), Photo Library **Colorize selected**, dashboard recent batches
- API: `GET /batches`, `POST /batches`, `GET /batches/stats`, `GET /batches/{batch_id}`, `PATCH /batches/{batch_id}`, `DELETE /batches/{batch_id}`, `POST /batches/{batch_id}/run`, `GET /batches/{batch_id}/manifest/download`
- Job: the colorize runner thread (`service/colorize_runner.py`), see [Colorization](colorization.md)

## Core Functions
- `services/api/app/service/batches.py`: `create_batch`, `list_batches`, `get_batch`, `update_batch`, `delete_batch`, `run_batch`, `manifest_download_url`
- `services/api/app/service/colorize_runner.py`: `enqueue`, `run_batch_now`, `recount`, `final_status`, `recover_interrupted`
- `services/api/app/repo/batch_store.py`: `save`, `load`, `list_records`, `mutate`, `delete_with_prefixes`
- `services/api/app/repo/manifest.py`: `build_manifest`, `MANIFEST_COLUMNS`
- `services/api/app/service/keys.py`: the key layout and `output_keys` (unique per batch)
- `apps/web/src/components/batches/`: `create-batch-dialog.tsx`, `edit-batch-dialog.tsx`, `batch-detail-view.tsx`, `batches-table.tsx`
- `apps/web/src/lib/queries.ts`: `useBatches`, `useBatch` (polls while active), `useCreateBatch`, `useUpdateBatch`, `useDeleteBatch`, `useRunBatch`, `useManifestDownload`
- `apps/web/src/lib/batch-labels.ts`: selector options and status copy

## Canonical Files
- Pattern exemplar for the create/edit forms: `apps/web/src/components/settings/settings-form.tsx`
- Router: `services/api/app/runtime/batches.py`

## Inputs
- `CreateBatchRequest`: `name` (1-120 chars), `description?`, `all_unprocessed` or `source_keys` (direct children of `colorization/grayscale/`), `model_id` (`ddcolor_artistic` default, `ddcolor_modelscope`, `ddcolor_paper`, `ddcolor_paper_tiny`), `input_size` (256 / **512**), `output_format` (**jpeg** / png / webp), `make_comparisons` (**true**), `run_now` (**true**)
- `UpdateBatchRequest`: `name?`, `description?` only. The configuration is immutable after creation because it defines what the outputs and manifest mean
- `batch_id`: `b-YYYYMMDD-HHMMSS-<6 hex>`; anything else is a 404

## Outputs
- `Batch`: id, name, description, configuration, `status` (`draft`, `queued`, `running`, `done`, `partial`, `failed`, `interrupted`, `cancelled`), `stage` (`preparing_model` / `downloading_model` / `loading_model` while a queued batch prepares its model; `reading_photo` / `colorizing_photo` / `saving_result` for the running photo, `saving_manifest` at the end; null once settled), `model_download_bytes`, `photo_count`, `done_count`, `failed_count`, `original_bytes`, `derived_bytes`, `manifest_key`, timestamps
- `BatchDetail`: `Batch` + `model_version` (`<model_id>@<Hugging Face revision sha>`) + `items[]` with per-photo status, error, dimensions, duration and 1-hour inline presigned URLs for original, colorized and comparison
- Side effects in B2: `colorization/batches/<id>.json` (record), `colorized/<id>/<stem>.<ext>`, `comparisons/<id>/<stem>.jpg`, `manifests/<id>.csv`
- Manifest CSV columns: `original_key, colorized_key, comparison_key, model_id, model_version, input_size, output_format, width, height, original_bytes, colorized_bytes, duration_ms, status, error, processed_at` (ISO 8601 UTC)

## Flow
- Create: resolve sources (a `list_objects_v2` of `grayscale/`; "all not yet colorized" excludes originals with a `done` item in any batch) -> `put_object` the record (`draft`, or `queued` when `run_now`) -> enqueue
- Run / re-run: refused with 409 while `queued`/`running` and with 503 when the ML stack is missing; otherwise status `queued`, enqueue. A `done` batch resets every item; any other settled batch (`partial`, `failed`, `interrupted`, `cancelled`) keeps its `done` items and resets only the rest, so the button reads "Re-run N unfinished photos". A re-run overwrites this batch's re-run outputs and rewrites its manifest; other batches' versions are untouched. To try another checkpoint on the same photos, **Colorize again with another model** opens the New batch dialog preselected with the batch's photos and settings and another model
- Worker: `running` -> per photo colorize and write, persisting the record after each (best-effort: a failed record PUT is logged and healed by the next one, see docs/RELIABILITY.md) -> manifest -> `done` (all ok), `partial` (some failed) or `failed` (none ok). The detail page shows the current photo and step ("Photo 2 of 4, x.jpg: saving the result to B2...")
- Edit: `mutate()` changes name/description only, safe while the batch runs
- Cancel (`POST /batches/{id}/cancel`): 409 unless `queued`/`running`; otherwise status `cancelled`. The worker stops at its next check (every few seconds during a model download, or before the next photo); finished photos keep their outputs, the rest stay `pending`. A cancelled batch can be re-run or deleted. The detail page flips the badge optimistically and labels the buttons "Cancelling..." / "Queuing..." while the request is in flight
- Delete: 409 while active; otherwise `delete_objects` on the batch's `colorized/` and `comparisons/` prefixes, its manifest and its record. Originals are never deleted

## Edge Cases
- Every original already colorized + "All not yet colorized" -> 400 with a message
- A chosen key that is not an ingested original -> 400
- Two originals with the same stem in one batch (`a.png`, `a.tif`) -> outputs `a.jpg`, `a-2.jpg`
- One undecodable photo -> that item `failed` with the error, batch `partial`
- Model cannot load (weights unreachable) -> every item `failed` with that error, manifest still written, batch `failed`
- API restarted mid-run -> batch `interrupted` at next startup, re-runnable
- Create with `run_now` and no ML stack -> 503 before anything is saved; with `run_now` off a draft is saved

## UX States
- Empty: "No batches yet" with the New batch action
- Loading: skeleton rows; detail page skeleton
- Error: inline `ErrorState` with Retry; mutation errors as toasts (503 says "DDColor is not installed" and shows the install command)
- Active: status badge spinner, progress bar, polling every 2 s

## Verification
- Test files: `services/api/tests/test_batches.py`, `services/api/tests/test_b2_resilience.py`, `services/api/tests/test_colorization_assets.py`, `apps/web/src/lib/batch-labels.test.ts`
- Required cases: create+run writes outputs/comparisons/manifest at original size; partial batch; 503 without ML; edit limited to name/description; delete keeps originals; re-run with another model keeps both versions; cancel queued -> re-run/delete; worker skips a cancelled batch; cancel mid-download stops the load; stalled download raises; 404/409 paths; restart -> `interrupted` -> re-runnable; engine failure still writes a manifest; record PUT timeouts never fail a batch or a model load; partial re-run retries only unfinished photos; presigned URLs stable across polls
- Focused verify command: `pnpm test:api`
- Default pre-PR verify command: `pnpm verify`
- Full local verify command: `pnpm verify:full` when E2E/live prerequisites apply
- Pass criteria: all of the above green; a real run with `pnpm setup:ml` produces `done` items whose `width`/`height` equal the originals'

## Related Docs
- [Colorization](colorization.md)
- [Photo Library](photo-library.md)
- [ARCHITECTURE.md](../../ARCHITECTURE.md)
- [docs/app-workflows.md](../app-workflows.md)
