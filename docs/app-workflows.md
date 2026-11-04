<!-- last_verified: 2026-11-04 -->
# App Workflows

User journeys inside the application.

## Run a Colorization Batch

- User opens `/batches` and clicks **New batch** (or selects photos in the Photo Library and clicks **Colorize selected**, which opens the same dialog with those photos pre-chosen)
- The form uses selectors only: photos (**All not yet colorized** or **Choose photos** with a checklist), model (`Select` with a one-line description per DDColor checkpoint), input size (256 / 512), output format (JPEG / PNG / WebP), side-by-side comparisons (switch), run now (switch). Defaults are pre-selected and explained under each field: DDColor tiny, 512, JPEG, comparisons on, run now on; the name field shows only a placeholder ("Archive box 1")
- On create the user lands on `/batches/<id>`. With **Run now** off the batch is a `draft` with a **Run** button
- If the optional ML stack is not installed, creating with Run now (or pressing Run) shows a toast with the API's 503 message, which names `pnpm setup:ml`; nothing is queued
- While the batch is `queued` or `running` the page polls every 2 s: the progress bar, per-photo status badges and the gallery fill in as the worker finishes each photo
- Each finished photo shows a before/after slider (drag to reveal the colorized version) and, when comparisons are on, a toggle to the side-by-side composite. A failed photo shows its error; the rest of the batch continues and the batch ends `partial`
- **Manifest CSV** downloads the per-run manifest through a fresh presigned URL
- **Edit** opens a dialog pre-filled with name and description; the model configuration is shown read-only because it defines what the outputs mean
- **Re-run** (on `done`, `partial`, `failed` or `interrupted`) overwrites that batch's own outputs and manifest. To compare models, create another batch: both versions are kept
- **Delete** asks for confirmation, stating that the colorized outputs, comparisons, manifest and record are removed and the originals are kept. Delete and Re-run are disabled while the batch is queued or running
- If the API restarts mid-run, the batch reappears as `interrupted` with a Re-run button rather than spinning forever
- See: [Batches](features/batches.md)

## Browse Originals and Colorized Versions

- User opens `/photos`: a grid of grayscale originals, newest first, 48 per page with Previous / Next
- Each card shows the latest colorized version when there is one (otherwise the original), a version count badge ("grayscale" when none) and a "was color" badge for scans that arrived in colour
- Ticking cards and clicking **Colorize selected (N)** starts a batch over exactly those photos
- Clicking a card opens a side sheet with a before/after slider for the latest version and a list of every version across batches (batch name linking to the batch, model, input size, size, time) with a download button each
- Empty library: a prompt to ingest scans or run `pnpm seed:demo`
- See: [Photo Library](features/photo-library.md)

## Ingest Photos

- User opens `/upload` (**Bulk Ingest** in the sidebar) and drops many scans or picks them; the picker accepts JPEG, PNG, TIFF, WebP and BMP, up to 100 MB each
- Each file uploads **directly from the browser to B2** with a presigned PUT into `colorization/grayscale/`. A determinate bar tracks the bytes; then the row switches to "Verifying upload..." while the API checks the stored object's type signature and measures its colour saturation
- A colour photo is accepted and flagged; it shows a "was color" badge in the Photo Library and is desaturated before inference
- The queue survives navigation (an "Uploading N files" indicator stays in the header) and a reload mid-upload asks for confirmation
- A file with the same name replaces the earlier original at the same key (B2 keeps the previous version)
- See: [Bulk Ingest](features/file-upload.md)

## View Dashboard

- User opens `/`
- The headline card is the **write-amplification ratio**: stored bytes per ingested byte under `colorization/` (originals plus every colorized output, comparison and manifest)
- Three more cards: photos ingested, photos colorized (originals with at least one successful version) and batches run
- A bar chart compares grayscale bytes with derived bytes; a table lists the five most recent batches with status, progress and derived bytes, linking to each batch
- While any recent batch is running, the dashboard refreshes every 4 s
- See: [Dashboard](features/dashboard.md)

## Browse the Bucket

- User opens `/files` (**Bucket Explorer**): the whole bucket, newest 100 objects, in a folder tree, so the app's `colorization/` objects appear next to anything else in the bucket
- Clicking a file opens a preview with its metadata, download and delete; **Detailed metadata** recomputes checksums and image fields on demand
- By-key preview, download, detail and delete are confined to `colorization/` by default (`ALLOWED_KEY_PREFIX`); objects outside it are listed but answer 400 when opened
- Deleting a colorized output here does not update its batch record; use batch delete to remove a batch's outputs consistently
- See: [Bucket Explorer](features/file-browser.md)

## Change Preferences

- User navigates to `/settings`
- A banner at the top states that the page is mostly a demonstration: only Theme is wired up for real
- **Theme** (real): saving applies and persists it (`next-themes`); the header toggle drives the same state
- **Profile and preference fields** (demo): each is labelled "Demo field", persists to `localStorage` only, and drives no behaviour
- Saving reports honestly which part was applied and which was only stored locally
- Danger Zone actions are a demo; no real delete runs
- See: [Settings](features/settings.md)
