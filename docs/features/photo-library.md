<!-- last_verified: 2026-11-04 -->
# Feature: Photo Library

## Purpose
Show the archive the way an archivist thinks about it: one card per original, with every colorized version across batches one click away, scoped to this app's prefix (the Bucket Explorer remains the full-bucket view).

## Used By
- UI: `/photos` (grid, multi-select, **Colorize selected**), the photo detail sheet, the create-batch dialog's photo checklist
- API: `GET /photos?limit=&cursor=`, `GET /photos-by-key/detail?key=`

## Core Functions
- `services/api/app/service/photos.py`: `list_photos`, `get_photo_detail`, `_versions_by_original`
- `services/api/app/service/upload.py`: `check_color` (writes the `was_color` marker at ingest)
- `apps/web/src/app/photos/page.tsx`, `apps/web/src/components/photos/photo-detail-sheet.tsx`, `apps/web/src/components/common/before-after-slider.tsx`
- `apps/web/src/lib/queries.ts`: `usePhotos`, `usePhotoDetail`

## Canonical Files
- Router: `services/api/app/runtime/photos.py`

## Inputs
- `limit`: 1-200 (default 48); `cursor`: the opaque `next_cursor` from the previous page
- `key`: a direct child of `colorization/grayscale/`

## Outputs
- `PhotoPage`: `items[]` + `next_cursor`
- `Photo`: key, filename, size, last_modified, `was_color`, `colorized_versions`, inline presigned `original_url` and `colorized_url` (latest version)
- `PhotoDetail`: `Photo` + `versions[]` (batch id and name, model, input size, colorized and comparison keys, size, processed_at, inline `colorized_url` / `comparison_url`, attachment `download_url`), newest first

## Flow
- `list_objects_v2` of `grayscale/` (direct children only), sorted newest first, sliced by cursor
- Versions come from the batch records (`done` items only), grouped by original key
- `was_color` is one `list_objects_v2` of `flags/was-color/`: a marker exists only for originals the ingest check measured as colour (mean HSV saturation above 0.18)
- URLs are signed per response; they last `PRESIGN_VIEW_EXPIRY_SECONDS` (1 hour)

## Edge Cases
- Key outside the library (another prefix, or a nested path) -> 400; missing original -> 404
- Invalid cursor -> 400
- Original deleted through the Bucket Explorer -> disappears from the library; its versions stay in their batches
- TIFF and BMP originals may not render in every browser; the colorized versions (JPEG/PNG/WebP) always do
- Sepia-toned prints can measure above the threshold and be flagged `was color`; the flag is informational only

## UX States
- Empty: prompt to ingest or run `pnpm seed:demo`
- Loading: skeleton tiles; Error: `ErrorState` with Retry
- Card badges: version count ("grayscale" when none), "was color"
- Detail sheet: before/after slider for the latest version, or the original with a hint when not colorized yet

## Verification
- Test files: `services/api/tests/test_photos.py`, `services/api/tests/test_batches.py::test_rerun_with_another_model_keeps_both_versions`
- Required cases: originals-only listing and pagination, bad cursor, colour flagging, library-only keys
- Focused verify command: `pnpm test:api`
- Default pre-PR verify command: `pnpm verify`
- Full local verify command: `pnpm verify:full` when E2E/live prerequisites apply
- Pass criteria: tests green

## Related Docs
- [Batches](batches.md)
- [Bulk Ingest](file-upload.md)
- [docs/app-workflows.md](../app-workflows.md)
