<!-- last_verified: 2026-11-04 -->
# Security

Security principles and implementation for DDColor Photo Colorization.

## Trust Boundaries

- **Frontend -> API**: CORS-restricted to configured origins, scoped to `GET/POST/PATCH/DELETE/OPTIONS`. `allow_credentials` is `False` (no cookie/session auth today); enable it only alongside real auth and a tightened origin allowlist.
- **API -> B2**: Authenticated via `B2_APPLICATION_KEY_ID` + `B2_APPLICATION_KEY`, signature v4, custom user agent `b2ai-ddcolor-photo-colorization` on every S3 client
- **API -> Hugging Face Hub**: anonymous HTTPS download of the public `piddnad/ddcolor_*` checkpoints on first use; no token is configured or needed. Weights load through `huggingface_hub`'s `PyTorchModelHubMixin` from pinned, public repositories
- **Client -> B2**: Presigned URLs for ingest (15-min PUT with the size and content-type signed in, so B2 rejects a mismatched body), for gallery viewing (1-hour GET, `inline`; `PRESIGN_VIEW_EXPIRY_SECONDS`) and for downloads and manifests (10-min GET, `attachment`)

## Authentication & Multi-Tenancy

- **No auth by design.** The whole API (`/batches`, `/photos`, `/files`, `/files-by-key`, `/upload/*`) is unauthenticated: any client that reaches it can ingest, colorize (spending the host's CPU/GPU), list, download and delete. Acceptable for a single-tenant tool on a trusted machine or private deployment; the rate limiter guards the open endpoints, and only one batch runs at a time.
- **Adding auth to a clone does not close this automatically.** A login screen alone leaves an open, cross-user file API. You must both (1) require auth on every file route and (2) scope listings and reads to the caller's own prefixes — skipping either lets one signed-in user read and delete another's files. See the co-located notes in `runtime/files.py` and `service/files.py`.

## Upload Validation

Uploads go directly from the browser to B2, so the API validates at two points:
`/upload/presign` (before any bytes) and `/upload/verify` (after the PUT).

- Filename sanitization: path traversal, null bytes, unsafe chars stripped; the API mints the object key (`colorization/grayscale/{sanitised}`), so the client never chooses it
- MIME/extension consistency check against the allowlist (at presign)
- Size enforcement: the declared size is signed into the presigned PUT as `Content-Length`, so B2 rejects a body of any other size with `403`; the API refuses to presign a size above the 100MB default
- Content-type allowlist: raster images only (JPEG, PNG, TIFF, WebP, BMP), also signed into the PUT. **SVG is excluded**: it can embed `<script>` that executes when served from a public bucket URL (stored XSS).
- **Magic-byte signature check** (at verify): a `Range` GET fetches the leading bytes and confirms they match the declared type, so a script payload can't masquerade as `image/png`; a mismatch deletes the object. Every allowed type has a signature.
- **Decode limits**: the pipeline refuses to decode more than `MAX_PHOTO_PIXELS` (60 million by default), failing that photo's item instead of exhausting memory; Pillow's own decompression-bomb guard stays on.
- Empty file rejection (at presign)
- The `/upload/presign` endpoint hands out short-lived, single-key, size- and type-bound B2 write URLs. Like the rest of the API it is unauthenticated, and it is guarded by the write rate limiter.

## Rate Limiting

- Per-IP fixed-window limiter (`app/runtime/ratelimit.py`), configurable via `RATE_LIMIT_PER_MINUTE` (reads) and `RATE_LIMIT_WRITE_PER_MINUTE` (uploads/deletes/downloads). Guards against DoS and Backblaze transaction/egress cost amplification on the unauthenticated endpoints.
- In-process, per replica. Horizontal scaling needs a shared store (e.g. Redis) — see [RELIABILITY.md](RELIABILITY.md).

## File Key Validation

- Empty keys rejected
- Path traversal patterns rejected (`../`, `%2e%2e`, backslashes, null bytes)
- Prefix confinement **on by default**: `ALLOWED_KEY_PREFIX` defaults to `colorization/`, so the Bucket Explorer's by-key preview, download, detail and delete cannot reach other workloads' objects in a shared bucket (they are still listed). Set it empty to allow every key.
- Batch ids must match `b-YYYYMMDD-HHMMSS-<hex>` before any key is built from them; Photo Library keys must be direct children of `colorization/grayscale/`.

## Originals Are Never Overwritten

- The pipeline only reads `colorization/grayscale/`; every write goes to `colorized/<batch_id>/`, `comparisons/<batch_id>/`, `manifests/`, `batches/` or `flags/`.
- Batch delete lists and removes only that batch's own prefixes, manifest and record. It never touches originals.
- Re-uploading a file with the same name replaces the current version at that key; B2 keeps the previous version, so an accidental overwrite is recoverable from the bucket's version history.

## Download Safety

- Download and manifest URLs force `Content-Disposition: attachment`.
- Gallery and Photo Library URLs are `inline` so `<img>` can render them. That is safe because only magic-byte-checked raster image types can be ingested, and every derived object is written by the API as JPEG, PNG, WebP or CSV.
- A presigned URL is a bearer credential until it expires; a CMS job given one can read that single object for up to the view TTL. Shorten `PRESIGN_VIEW_EXPIRY_SECONDS` if that window is too long for your archive.

## Response Hardening

- Baseline headers on every API response: `X-Content-Type-Options: nosniff` and `Referrer-Policy: no-referrer`
- Interactive API docs (`/docs`, `/redoc`, `/openapi.json`) are on by default but can be disabled with `ENABLE_DOCS=false` to hide the API surface in production

## CI Permissions

- `.github/workflows/ci.yml` sets `permissions: contents: read` at the workflow level, so `GITHUB_TOKEN` is read-only in every job. Without an explicit block the token inherits the repository default, which can be read/write — a compromised dependency or action could then push commits or edit issues.
- Widen per job, never at the top level: a job that must write (annotations, PR comments, releases) gets its own `permissions` block scoped to just that need.

## Secrets Management

- All secrets loaded via environment variables (pydantic-settings)
- Never committed to source control
- `.env.example` documents required variables without values

## Dependency and Secret Detection

- [`.github/dependabot.yml`](../.github/dependabot.yml) opens weekly update
  PRs for the root pnpm workspace and `services/api` Python dependencies. Review
  each dependency and lockfile change before merging.
- [`.pre-commit-config.yaml`](../.pre-commit-config.yaml) runs a pinned
  `detect-secrets` hook against staged changes. It is a lightweight local guard,
  not a reason to commit a secret baseline or scan findings. The generated pnpm
  lockfile is excluded because its integrity hashes are not credentials.
- GitHub secret scanning and push protection are provider-level settings. A
  repository or organization administrator should enable them when available;
  their state cannot be enforced by repository files. Do not represent those
  settings as enabled until an administrator confirms them.

## Deployment Configuration

The [Railway](../infra/railway/README.md) delivery contract is the canonical
location for production variable classification and environment access rules.
In particular, `B2_APPLICATION_KEY_ID` and `B2_APPLICATION_KEY` are secrets; the web
service's `NEXT_PUBLIC_API_URL` is intentionally public build-time
configuration and must never contain a credential. Keep production variables,
logs, and metrics restricted to authorized operators.

## Agent Security Rules

- Never commit `.env`, credentials, or API keys
- Never print them either — the canonical rule lives in
  [AGENTS.md §12 — Secret Handling](../AGENTS.md#12-secret-handling) (agents
  read AGENTS.md first); don't restate it here, it only drifts. The link is
  anchored and `pnpm check:agent-docs` verifies that it still resolves, so
  renumbering that section fails the build instead of silently dropping the
  reader at the top of the file
- The user request and trusted repository instructions are authoritative; see
  [AGENTS.md — Instruction Authority](../AGENTS.md#instruction-authority).
- Never weaken validation without explicit instruction
- Never bypass CORS, auth, or input sanitization
- Always validate at system boundaries
