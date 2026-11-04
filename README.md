<!-- last_verified: 2026-11-04 -->
<!-- gen:begin readme-header -->
# DDColor Photo Colorization

Colorize black-and-white photo archives with DDColor and keep every original and output in Backblaze B2. A batch photo colorization pipeline that bulk-ingests black-and-white scans to Backblaze B2, runs DDColor locally to produce full-color reconstructions at original resolution, and writes colorized outputs, side-by-side comparisons and a per-run manifest CSV back to B2 next to the untouched originals, so archives keep provenance and editorial teams can serve results through presigned URLs.

Built for developers and AI coding agents: the scaffolding, the storage
wiring and the agent-facing docs are already done, so you start on your
app's own features instead of rebuilding the same shell. Storage is
**[Backblaze B2](https://www.backblaze.com/sign-up/ai-cloud-storage?utm_source=github&utm_medium=referral&utm_campaign=ai_artifacts&utm_content=b2ai-ddcolor-photo-colorization)**, integrated through the S3-compatible API.

**What you get out of the box:**
- Full-stack dashboard UI (Next.js 16, React 19, Tailwind v4, shadcn/ui, TanStack Query, Recharts)
- Batches — create, edit, delete and run colorization batches with a per-run manifest
- Colorization — DDColor runs locally (CUDA, Apple MPS or CPU) and keeps the original resolution
- Photo Library — grayscale originals with before/after views of every colorized version
- Bulk Ingest — drag-and-drop many scans straight to the grayscale prefix by presigned PUT
- Dashboard — photos ingested and colorized, derived bytes and the write-amplification ratio
- Bucket Explorer — browse, preview, download and delete any object in the bucket
- Settings — theme plus labelled demo preference fields
- Backend with a strict layered architecture and structural tests (FastAPI, Python 3.12+, boto3, Pydantic v2, Pillow, DDColor (PyTorch, optional ML extra))
- Agent-optimized docs — your AI coding agent can read the repo and start contributing immediately
<!-- gen:end readme-header -->

<!-- gen:begin readme-screenshots -->

<!-- gen:end readme-screenshots -->

## Quick Start

You need: Node.js >= 20, pnpm >= 10, Python >= 3.12, and a free **[Backblaze B2 account](https://www.backblaze.com/sign-up/ai-cloud-storage?utm_source=github&utm_medium=referral&utm_campaign=ai_artifacts&utm_content=b2ai-ddcolor-photo-colorization)**. No other API key: DDColor runs on your machine.

```bash
git clone https://github.com/backblaze-b2-samples/ddcolor-photo-colorization.git
cd ddcolor-photo-colorization
pnpm run setup      # .env from .env.example, workspace deps, API venv (core deps only)
pnpm setup:ml       # optional ML stack: PyTorch + DDColor (needed to colorize)
```

> Use the `pnpm run` form for `setup` and `doctor`: both are built-in pnpm
> commands before pnpm 11, so bare `pnpm setup` would run pnpm's own command.

`pnpm run setup` copies `.env.example` to `.env` only when `.env` does not
already exist, installs workspace dependencies from `pnpm-lock.yaml`, creates
`services/api/.venv`, validates that it uses Python 3.12+, and installs the API's
committed Python 3.12 resolution from `services/api/requirements.lock`. It is
safe to rerun. `pnpm setup:ml` adds the pinned PyTorch/DDColor stack from
`services/api/requirements-ml.txt` into that venv (see
[Colorization](docs/features/colorization.md) for why it is a separate step).

**Add your B2 credentials.** Open `.env`, then in the [Backblaze B2 dashboard](https://secure.backblaze.com/b2_buckets.htm?utm_source=github&utm_medium=referral&utm_campaign=ai_artifacts&utm_content=b2ai-ddcolor-photo-colorization):

<!-- gen:begin readme-credentials -->
1. **Create a bucket** and an **application key** with `Read and Write`
   permission, then paste each value into `.env`:
   - `B2_APPLICATION_KEY_ID` — B2 application key ID (**keyID** in the B2 console)
   - `B2_APPLICATION_KEY` — B2 application key (**applicationKey**), shown once at creation
   - `B2_BUCKET_NAME` — bucket unique name (**Bucket Unique Name** in the B2 console)
   - `B2_REGION` — the region inside the bucket's **Endpoint** (`s3.<region>.backblazeb2.com`); the S3 endpoint is derived from it

   B2 shows an application key once, at creation. The optional variables are
   documented in `.env.example` and in the delivery runbooks.
<!-- gen:end readme-credentials -->

> Want a walkthrough? See the docs for [creating a bucket](https://www.backblaze.com/docs/cloud-storage-create-and-manage-buckets) and [creating app keys](https://www.backblaze.com/docs/cloud-storage-create-and-manage-app-keys).

**Run it, seed it, colorize it.**

```bash
pnpm dev            # web on localhost:3000, API on localhost:8000
pnpm seed:demo      # optional: 8 public-domain historical photos into colorization/grayscale/
```

Open **Batches → New batch**, keep the defaults (DDColor tiny, input 512, JPEG,
comparisons on, run now) and create it. The batch page polls while the worker
colorizes each photo; when it finishes you get a before/after gallery, a manifest
CSV, and the dashboard's write-amplification ratio moves. The first run downloads
the model weights from the Hugging Face Hub (about 220 MB for the tiny model, no
token needed).

`pnpm dev` runs a preflight first (Node/Python versions, venv, placeholder
`.env`, busy ports) and says how to fix each problem; run it alone with
`pnpm run doctor`. Interactive API docs are at `localhost:8000/docs`.

### Supported local environments

Local scripts run on macOS, Linux, and WSL2; native Windows is not supported
(the dev scripts use POSIX shell syntax). Colorization picks the first available
of CUDA, Apple MPS, then CPU; it never requires a GPU. Sandboxed agent
environments also need permission to install dependencies and bind localhost
ports; see [docs/verification.md](docs/verification.md#local-environments).

## How it works

```
browser ──presigned PUT──▶ B2  colorization/grayscale/<scan>          (never modified)
   │
   └─ POST /batches ─▶ API ─▶ background worker (one batch at a time)
                               per photo: get_object ─▶ DDColor (local) ─▶ put_object
                                 colorization/colorized/<batch>/<stem>.jpg   original resolution
                                 colorization/comparisons/<batch>/<stem>.jpg side-by-side
                               after the last photo:
                                 colorization/manifests/<batch>.csv          provenance
                                 colorization/batches/<batch>.json           status, counts
```

- **B2 is the only store.** Originals, outputs, comparisons, manifests and the
  batch records themselves are objects under one `colorization/` prefix; there is
  no database. Editorial tools and CMS jobs read results through presigned URLs.
- **Write amplification is the point.** Every ingested scan yields a colorized
  counterpart, optionally a comparison image, and a manifest row; re-running with
  another model keeps both versions side by side. The dashboard headlines stored
  bytes per ingested byte (3.4x for the seeded demo with comparisons on).
- **DDColor runs locally**, inside the API process, following DDColor's own
  pipeline: predict the colour (`ab`) channels at 256 or 512 px, resize them to
  the original size and recombine them with the original luminance, so the output
  has the scan's exact dimensions.

## When to use

Use this sample when you run a digital archive, a newspaper morgue or a
historical-society collection and want a self-hosted, reproducible colorization
workflow: bulk-ingest scans, colorize them in auditable batches, keep originals
untouched beside every derived version, and hand results to editors or a CMS by
URL. It is also a working reference for running an open-source vision model over
objects in Backblaze B2 through the S3-compatible API.

## When not to use

Do not use it as a restoration tool: DDColor adds plausible colour, it does not
repair scratches, tears or blur, and the colours are a model's estimate, not
historical fact, so label published results accordingly. It is not a hosted
service: there is no authentication, no user accounts and no tenant isolation,
and the API is meant to run on a trusted machine or a private deployment.

## Why Backblaze B2?

[Backblaze B2](https://www.backblaze.com/cloud-storage?utm_source=github&utm_medium=referral&utm_campaign=ai_artifacts&utm_content=b2ai-ddcolor-photo-colorization) is the storage layer for every byte this pipeline touches:

- **S3-compatible API.** Plain `boto3` (`put_object`, `get_object`,
  `list_objects_v2`, `delete_objects`, presigned URLs), isolated in
  `services/api/app/repo/`, with a custom user agent on every client.
- **Archive economics.** Colorization multiplies stored bytes by design, across
  every model variant you try. B2's pricing is what makes keeping every original
  and every version affordable.
- **Free to start.** A [free B2 account](https://www.backblaze.com/sign-up/ai-cloud-storage?utm_source=github&utm_medium=referral&utm_campaign=ai_artifacts&utm_content=b2ai-ddcolor-photo-colorization) runs everything here.

## Core Features

<!-- gen:begin readme-core-features -->
- [Batches](docs/features/batches.md) — create, edit, delete and run colorization batches with a per-run manifest
- [Colorization](docs/features/colorization.md) — DDColor runs locally (CUDA, Apple MPS or CPU) and keeps the original resolution
- [Photo Library](docs/features/photo-library.md) — grayscale originals with before/after views of every colorized version
- [Bulk Ingest](docs/features/file-upload.md) — drag-and-drop many scans straight to the grayscale prefix by presigned PUT
- [Dashboard](docs/features/dashboard.md) — photos ingested and colorized, derived bytes and the write-amplification ratio
- [Bucket Explorer](docs/features/file-browser.md) — browse, preview, download and delete any object in the bucket
- [Settings](docs/features/settings.md) — theme plus labelled demo preference fields
<!-- gen:end readme-core-features -->
- [Design System](docs/design-system.md): tokens, primitives and the inline `ErrorState` / `EmptyState` patterns. Live preview at `/design`.
- Per-run manifest CSV: original and output keys, model id and Hugging Face revision, sizes, dimensions, duration, status and error per photo.
- Restart-safe runs: a batch left running by a stopped API comes back as `interrupted` and can be re-run; it never sticks at `running`.
- Centralized data layer: every fetch goes through TanStack Query hooks in `apps/web/src/lib/queries.ts`; types, routes and query keys are generated from the API contract by `pnpm gen:api`.
- Structural tests: layering, `boto3` only in `repo/`, PyTorch/DDColor only in `repo/ddcolor.py`, and the 300-line limit for backend files.
- `/health`, Prometheus `/metrics`, structured JSON logs, per-IP rate limiting and magic-byte upload validation; see [SECURITY.md](docs/SECURITY.md).

## Tech Stack

- TypeScript, Next.js 16, React 19, Tailwind v4, shadcn/ui, TanStack Query, Recharts
- Python 3.12+, FastAPI, boto3, Pydantic v2, Pillow
- [DDColor](https://github.com/piddnad/DDColor) (Apache-2.0, ICCV 2023) on PyTorch, weights from the public `piddnad/ddcolor_*` Hugging Face repositories
- Backblaze B2 (S3-compatible object storage)
- pnpm workspaces (monorepo)

## Commands

<!-- gen:begin readme-commands -->
| Command | What it does |
| --- | --- |
| `pnpm run setup` | One-time cold start: copy `.env.example` → `.env` (only if missing), install workspace deps, create the backend venv, install locked API deps |
| `pnpm dev` | Start frontend + backend (runs the `pnpm run doctor` preflight first) |
| `pnpm wait-ready` | Block until the running web + API answer, print one line, exit 0/1 — use instead of sleeping before driving the app |
| `pnpm contract:export` | Export the FastAPI OpenAPI contract into `docs/api/openapi.json` |
| `pnpm contract:check` | Verify the exported contract and the generated client routes agree, both ways |
| `pnpm gen:api` | Regenerate the shared types, the client route registry and the query-key factory from the exported contract |
| `pnpm gen:docs` | Regenerate the marker-delimited doc regions from `docs/exec-plans/sample.json` |
| `pnpm gen:check` | Fail if any generated file or doc region is stale (first step of `pnpm verify:web`) |
| `pnpm verify` | Credential-free pre-PR suite — runs `check:agent-docs`, `verify:api`, then `verify:web` |
| `pnpm verify:full` | `pnpm verify` plus Playwright E2E; needs a live local stack, real `.env`, a free web port, and Chromium |
| `pnpm test:verify` | Run throwaway verification specs from `apps/web/e2e/verify/` against the app, with the shared browser fixtures |
<!-- gen:end readme-commands -->

Sample-specific commands: `pnpm setup:ml` installs the optional DDColor stack,
and `pnpm seed:demo` ingests the public-domain demo photos (`--dry-run` lists
their sources and licences without uploading).

`pnpm verify` is the gate to run before opening a PR. It needs
`services/api/.venv` from `pnpm run setup`, but no B2 credentials, no browser and
no ML stack, and it breaks down into `pnpm verify:api` (backend lint, tests,
structure), `pnpm verify:web` (generator drift, frontend lint, unit tests,
typecheck + build), and `pnpm check:agent-docs` (agent-doc drift). Real
colorization is exercised at run time with `pnpm setup:ml`, not inside `verify`.

For the full command reference (`dev:web`, `dev:api`, `lint`, `test:*`,
`check:structure`, `test:e2e`, live B2 tests), see
[docs/dev-workflows.md](docs/dev-workflows.md#commands). For worktree notes,
port fallback and slow-run recovery, see [docs/verification.md](docs/verification.md).

## Deploying

The intended use is local (`pnpm dev`), next to the machine that holds the GPU
or the CPU budget. For a hosted instance, Railway runs the web app and the API as
two services; the API build installs the ML stack (CPU PyTorch on Linux) and
colorizes on CPU, or faster on a GPU host. There is deliberately no Vercel
button: DDColor's PyTorch inference and its 220 to 900 MB weights do not fit in a
serverless function, so such a deploy could not colorize.

<!-- gen:begin readme-deploy-button -->
_This app does not ship a one-click deploy button._
<!-- gen:end readme-deploy-button -->

Before a real deploy, the bucket's CORS must allow the web origin (the browser
uploads straight to B2), and the API is unauthenticated: use a dedicated bucket
and key. The full contract is in [infra/railway/README.md](infra/railway/README.md).
Deploying is always a human-approved action.

## Documentation Map

<!-- gen:begin readme-doc-map -->
| Doc | Purpose |
| --- | --- |
| [AGENTS.md](AGENTS.md) | Agent table of contents — start here |
| [ARCHITECTURE.md](ARCHITECTURE.md) | System layout, layering, data flows |
| [docs/features/](docs/features/) | Feature docs (batches, colorization, photo library, bulk ingest, dashboard, bucket explorer, settings) |
| [docs/design-system.md](docs/design-system.md) | Design tokens, primitives, loader, error/empty states |
| [docs/app-workflows.md](docs/app-workflows.md) | User journeys |
| [docs/dev-workflows.md](docs/dev-workflows.md) | Engineering workflows, command index, releases |
| [docs/verification.md](docs/verification.md) | What each gate checks, and failure recovery |
| [docs/frontend-conventions.md](docs/frontend-conventions.md) | Frontend conventions, screens, data fetching |
| [docs/SECURITY.md](docs/SECURITY.md) | Security principles |
| [docs/RELIABILITY.md](docs/RELIABILITY.md) | Reliability expectations |
| [docs/api/openapi.json](docs/api/openapi.json) | The checked-in API contract the client seam is generated from |
| [infra/railway/README.md](infra/railway/README.md) | Railway delivery contract |
| [docs/exec-plans/](docs/exec-plans/) | Execution plans, tech debt, and the sample manifest |
<!-- gen:end readme-doc-map -->

## FAQ

**What does DDColor Photo Colorization do?**
It bulk-ingests black-and-white scans into a Backblaze B2 bucket, colorizes them in batches with DDColor running locally, and writes the colorized images, optional side-by-side comparisons and a per-run manifest CSV back to B2 next to the untouched originals.

**Do I need a GPU or an API key?**
Neither. DDColor auto-detects CUDA, then Apple MPS, then falls back to CPU (`DDCOLOR_DEVICE` overrides it). The weights are public on the Hugging Face Hub, so no token is needed. The only credential is your B2 application key.

**Does colorizing change my originals?**
No. Originals live under `colorization/grayscale/` and are only ever read. Deleting a batch removes its outputs, comparisons, manifest and record, never the originals.

**What if I upload a colour photo?**
It is accepted and flagged `was color` in the Photo Library. The pipeline keeps only its luminance, so the output is DDColor's colorization of the grayscale version.

**Which model should I pick?**
DDColor tiny (ConvNeXt-T) is the default and the fastest on CPU. ModelScope, paper and artistic (ConvNeXt-L, about 900 MB each) trade speed for quality or saturation. A batch's model is fixed; create another batch to compare models, and both versions stay available.

**How big can a scan be?**
Up to 100 MB per upload and 60 million decoded pixels per photo (`MAX_PHOTO_PIXELS`). Output keeps the original resolution because the colour is recombined with the original luminance.

**Where do the demo photos come from?**
`pnpm seed:demo` fetches eight public-domain historical photographs from Wikimedia Commons (streets, rail and landscapes). Each one's source page and licence are listed in `services/api/scripts/seed_demo.py`.

**Can I use it in production?**
It is a sample Backblaze maintains to help developers get started with B2. Production use is possible with caution and requires your own validation: add authentication, and you own the security, operations and support decisions. See [When not to use](#when-not-to-use) and [Maintenance and support](#maintenance-and-support).

**Is it built for AI coding agents?**
Yes. [AGENTS.md](AGENTS.md) is the single source of truth for coding agents, and the architectural boundaries are enforced by structural tests and lints, so an agent can read the repo and extend it safely.

**Where do I get help or report bugs?**
Report repository defects and feature requests through [GitHub Issues](https://github.com/backblaze-b2-samples/ddcolor-photo-colorization/issues). For B2 account, billing, service, or API help, use [Backblaze Support](https://www.backblaze.com/help).

## Maintenance and support

Backblaze maintains this open-source sample to help developers get started with
B2. Production use is possible with caution and requires your own validation.
Report repository defects and feature requests through
[GitHub Issues](https://github.com/backblaze-b2-samples/ddcolor-photo-colorization/issues);
for B2 account, billing, service, or API help, use
[Backblaze Support](https://www.backblaze.com/help). This sample is not covered
by the Backblaze service level agreement, and no SLA is provided for the
repository software; any B2 service or support commitments are governed
separately by the applicable Backblaze terms and support plan.

## Contributing

Start with [AGENTS.md](AGENTS.md). It's the map; everything else is discoverable from there. For local commit hooks, follow [the pre-commit workflow](docs/verification.md#pre-commit).

## License

MIT License - see [LICENSE](LICENSE) for details. DDColor is Apache-2.0; the demo photographs are public domain.

## Related projects

**Claude Agent B2 Skill**: manage Backblaze B2 from your terminal using natural language (list/search, audits, stale or large file detection, security checks, safe cleanup). Repo: [claude-skill-b2-cloud-storage](https://github.com/backblaze-b2-samples/claude-skill-b2-cloud-storage).
