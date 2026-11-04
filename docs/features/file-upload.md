<!-- last_verified: 2026-11-04 -->
# Feature: Bulk Ingest

## Purpose
Ingest many black-and-white scans from the browser **directly into Backblaze B2** under `colorization/grayscale/`, where they become the untouched originals every batch reads from. The bytes never pass through the API, so ingest is limited only by `MAX_FILE_SIZE` (100 MB default) per file.

## Used By
- UI: `/upload` (**Bulk Ingest** in the sidebar), upload form component
- API: `POST /upload/presign`, `POST /upload/verify`

## Core Functions
- `apps/web/src/lib/upload-queue-context.tsx`: `UploadQueueProvider` / `useUploadQueue()`, the app-wide queue mounted in the root layout, so an ingest survives navigation; a finished upload invalidates every cached query, so the Photo Library and dashboard refresh
- `apps/web/src/lib/upload-status.ts`: queue status labels and summaries
- `apps/web/src/lib/upload-file-types.ts`: `ACCEPTED_FILE_TYPES`, the dropzone allow-list mirroring the backend
- `apps/web/src/components/upload/`: `upload-form.tsx`, `dropzone.tsx`, `upload-progress.tsx`
- `apps/web/src/lib/api-client.ts`: `uploadFile()`: presign -> direct browser-to-B2 PUT (XHR for progress) -> verify
- `services/api/app/service/upload.py`: `_validate_declared`, `create_presigned_upload`, `verify_upload`, `check_color`
- `services/api/app/repo/b2_upload.py`: `generate_presigned_upload()`, `get_object_head_bytes()`, `invalidate_listing()`
- `services/api/app/repo/imaging.py`: `open_image`, `mean_saturation`, `is_color`

## Canonical Files
- Presign/verify handlers: `services/api/app/runtime/upload.py`
- Service: `services/api/app/service/upload.py`

## Inputs
- Presign: `{ filename, content_type, size_bytes }`; allowed types `image/jpeg`, `image/png`, `image/tiff`, `image/webp`, `image/bmp` with matching extensions (`jpg/jpeg/jfif`, `png`, `tif/tiff`, `webp`, `bmp`)
- Direct PUT: the raw bytes to the signed B2 URL
- Verify: `{ key }` (must be under `colorization/grayscale/`)

## Outputs
- Presign -> `PresignUploadResponse`: `key` (`colorization/grayscale/<sanitized filename>`), `url`, `method`, `content_type`, `headers`, `expires_in` (15 min)
- Verify -> `FileUploadResponse`: `key`, `filename`, `size_bytes`, `size_human`, `content_type`, `uploaded_at`, `url`, `was_color` (`true` colour, `false` grayscale, `null` if the check could not read the image), `metadata` (null; recomputed on demand by the Bucket Explorer)
- Side effects: the original in B2; for colour images, a small marker at `colorization/flags/was-color/<filename>` holding the measured saturation; `uploads_total` metric

## Flow
- Dropzone filters by type and size, then each file: `POST /upload/presign` (size and content-type signed into the URL) -> XHR `PUT` to B2 with a determinate progress bar -> "Verifying upload..." -> `POST /upload/verify`
- Verify: HEAD (size, type, extension) -> `Range` GET of the first 512 bytes and a magic-byte check (JPEG, PNG, TIFF `II*\0`/`MM\0*`, WebP `RIFF....WEBP`, BMP `BM`); any failure deletes the object -> invalidate the listing cache -> saturation check: download, decode, mean HSV saturation on a 256 px thumbnail; above 0.18 writes the `was-color` marker
- A colour photo is accepted; the pipeline keeps only its luminance before inference

## Edge Cases
- Non-image types (PDF, text, audio, video, archives) -> 415 at presign
- Extension does not match type -> 415
- Spoofed content (HTML named `.png`) -> 415 at verify and the object is deleted
- Over 100 MB -> 413; empty -> 400
- Same filename twice -> same key; the newer upload becomes the current version (B2 keeps the old one)
- Bucket CORS does not allow the web origin (deployed) -> the PUT fails with a message pointing at `services/api/scripts/setup_b2_cors.py`
- Saturation check fails (unreadable image) -> upload still succeeds, `was_color: null`, warning logged

## UX States
- Idle dropzone listing the accepted formats; per-file progress, verifying phase, success with a link onward, error with retry
- Header indicator "Uploading N files" while the queue runs on another page

## Verification
- Test files: `services/api/tests/test_upload_validation.py`, `services/api/tests/test_upload_conflict.py`, `services/api/tests/test_photos.py` (colour check), `apps/web/src/lib/upload-file-types.test.ts`, `apps/web/src/lib/upload-status.test.ts`
- Required cases: image-only allow-list (TIFF/BMP accepted, PDF/text/video rejected), signature checks for every type, prefix minting under `colorization/grayscale/`, verify accept/reject/delete paths, `was_color` reported and the marker written only for colour images
- Focused verify command: `pnpm test:api`
- Default pre-PR verify command: `pnpm verify`
- Full local verify command: `pnpm verify:full` when the E2E/live prerequisites in [Verification](../verification.md#non-live-verification) are available
- Pass criteria: focused tests and `pnpm verify` green

## Related Docs
- [Photo Library](photo-library.md)
- [ARCHITECTURE.md](../../ARCHITECTURE.md)
- [App Workflows](../app-workflows.md)
