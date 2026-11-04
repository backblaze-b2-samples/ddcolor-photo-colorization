<!-- last_verified: 2026-11-04 -->
# Feature: Dashboard

## Purpose
Show how much colorization the archive has seen and what it costs in storage, headlined by the write-amplification ratio: stored bytes per ingested byte.

## Used By
- UI: `/` (`components/dashboard/colorization-overview.tsx`)
- API: `GET /batches/stats`

## Core Functions
- `services/api/app/service/photos.py`: `get_stats`, `amplification_ratio`
- `apps/web/src/lib/queries.ts`: `useBatchStats` (refreshes every 4 s while a recent batch is active)
- `apps/web/src/lib/batch-labels.ts`: `formatRatio`

## Canonical Files
- Dashboard component: `apps/web/src/components/dashboard/colorization-overview.tsx`

## Inputs
- None

## Outputs
- `ColorizationStats`: `photos_ingested`, `photos_colorized` (originals with at least one `done` version), `batches_total`, `grayscale_bytes`, `derived_bytes` (colorized + comparisons + manifests), `amplification_ratio` = `(grayscale_bytes + derived_bytes) / grayscale_bytes` (0 when nothing is ingested), `recent_batches` (5)

## Flow
- One `list_objects_v2` of `colorization/`, summed by sub-prefix, plus the batch records
- UI: the amplification card, three count cards, a bar chart of grayscale vs derived bytes, and a recent-batches table linking to each batch

## Edge Cases
- Empty archive -> ratio shows "-", counts 0, empty recent-batches state
- Objects deleted through the Bucket Explorer are reflected in the byte sums immediately, while batch counts follow the records
- Batch records and `flags/` markers are not counted as derived bytes

## UX States
- Loading: skeleton values; Error: `ErrorState` with Retry; Empty: "No batches yet"

## Verification
- Test files: `services/api/tests/test_batches.py::test_rerun_with_another_model_keeps_both_versions` (stats after two batches), `apps/web/src/lib/batch-labels.test.ts`
- Focused verify command: `pnpm test:api`
- Default pre-PR verify command: `pnpm verify`
- Full local verify command: `pnpm verify:full` when E2E/live prerequisites apply
- Pass criteria: tests green; after the seeded demo batch with comparisons on, the ratio is above 1 (3.4x measured)

## Related Docs
- [Batches](batches.md)
- [docs/app-workflows.md](../app-workflows.md)
