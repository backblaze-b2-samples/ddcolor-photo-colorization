<!-- last_verified: 2026-11-04 -->
# Reliability

Reliability expectations and practices for this project.

## Health Checks

- `GET /health` verifies B2 connectivity and returns `healthy` or `degraded`
- Health endpoint is always available, even when B2 is down
- The B2 client bounds connection attempts to 5 seconds, socket reads to 30
  seconds, and standard retries to 3 total attempts. Normal tests mock this
  boundary and deny network access; real connectivity is opt-in through
  `RUN_LIVE_B2_TESTS=1 pnpm test:live:b2`.

## Error Handling

- HTTP handlers return structured error responses with appropriate status codes
- External service failures (B2) are caught and surfaced as 500/503 responses
- No unhandled exceptions leak stack traces to clients
- Uncaught exceptions are converted to a typed JSON 500 (`{"detail": "Internal server error"}`, modeled by `app.types.ErrorResponse`) by the catch-all in `timing_middleware`
- **Error responses carry CORS headers.** `CORSMiddleware` is registered LAST in `main.py` so it is the outermost middleware and wraps every response — including uncaught-exception 500s produced by the inner catch-all. This is intentional and load-bearing: if a 500 shipped without `Access-Control-Allow-Origin`, the browser would block it and the frontend would surface only an opaque "network error", hiding the real server bug. Regression-guarded by `tests/test_error_handling.py::test_unhandled_exception_500_carries_cors_headers`.

## Logging

- Structured JSON logging via Python stdlib
- Every request gets a `request_id` for tracing
- Log levels: ERROR for failures, WARNING for degraded state, INFO for requests

## Observability

- Request timing middleware logs duration for every request
- `/metrics` endpoint exposes basic Prometheus-format counters
- Upload success/failure counts tracked

## Stateful Counters — durability caveats

The download counter and the `/metrics` counters are **in-process, per replica**. Consequences to plan for before scaling:

- **Download counter** (`app/repo/counter.py`) persists to a JSON file at `DOWNLOAD_COUNT_FILE` (default `.data/download_count.json`, resolved from the repo root — deliberately outside `services/api/`, which `uvicorn --reload` watches, so a download never writes into the dev reloader's watch tree). On an ephemeral filesystem (Railway without a mounted volume) it **resets to 0 on every redeploy**. With multiple replicas or Function instances each keeps its own file/count. For durable, shared counts: mount a persistent volume or swap the adapter for Redis/DB.
- **`/metrics` counters** live in process memory and reset on restart. Behind a load balancer, each replica reports only its own slice — scrape with an instance label and aggregate, or push to a shared collector.

## Rate Limiting

- Per-IP fixed-window limiter (`app/runtime/ratelimit.py`); `RATE_LIMIT_PER_MINUTE` / `RATE_LIMIT_WRITE_PER_MINUTE` are the budgets. Rejected requests get `429` with a `Retry-After` header.
- Counters are in-process per replica; horizontal scaling needs a shared store (e.g. Redis) for a global limit.

## Colorization Runner

- **One worker, FIFO queue, one batch at a time** (`service/colorize_runner.py`). DDColor is memory-heavy (the large checkpoints are about 900 MB), so batches never run concurrently; a second batch waits as `queued`.
- **One resident model.** `repo/ddcolor.py` keeps a single checkpoint loaded; switching model evicts the previous one and frees the CUDA/MPS cache first.
- **Per-photo isolation.** A photo that fails (undecodable, over `MAX_PHOTO_PIXELS`, B2 error) marks only its item `failed` with the error; the batch continues and ends `done`, `partial` or `failed`. If the model itself cannot load, every item fails with that error and the manifest is still written, so the run is recorded.
- **Status is durable.** Progress is persisted to the batch record in B2 after every photo, so the batch page and dashboard reflect it even across API restarts.
- **Restart behaviour.** A stopped API cannot finish an in-flight batch. At the next startup a background thread marks every batch last written before that process started and still `queued`/`running` as `interrupted` (its in-progress item goes back to `pending`); the UI offers **Re-run**, which overwrites that batch's partial outputs. Disable with `RECOVER_BATCHES_ON_STARTUP=false`.
- **Single process.** The queue and the record lock are in-process. Run one API replica; several replicas would each run their own queue and could interleave writes to the same record.
- **ML stack absent.** Run requests return 503 with the install command (`pnpm setup:ml`) instead of queuing a batch that would fail.
- **Throughput** is dominated by the device and by B2 transfer time: DDColor tiny at 512 runs in well under a second per 1-megapixel photo on CPU or Apple MPS once warm (the first MPS call compiles kernels for several seconds); each photo also costs one `get_object` and two or three `put_object` calls.

## Graceful Degradation

- File listing returns empty list (not error) when B2 has no objects
- The ingest colour check never blocks an upload: an unreadable image is logged and reported as `was_color: null`
- Frontend shows skeleton states while loading, error states on failure — and, for the bucket-listing waits that can run for seconds, on-screen copy that escalates instead of silent skeletons (`lib/loading-progress.ts`)
- A full bucket listing (needed by both `/files` and `/files/stats`) is cached, warmed at startup, and served **stale-while-revalidate**: after the first scan, an expired entry is returned immediately while a background thread refreshes it, so a slow or failing B2 list never turns into a user-visible 8-20s wait. `LIST_CACHE_TTL_SECONDS` (default 300) bounds staleness for changes made outside this app; the app's own uploads and deletes invalidate the cache outright. A failed background refresh keeps serving the previous snapshot and is logged
- `WARM_LIST_CACHE_ON_STARTUP=false` skips the startup scan (offline dev, or when startup must not touch B2)

## Deployment

- The API contracts check `/health`; it confirms process readiness, but the
  response is still HTTP 200 when B2 is degraded. Promotion therefore also
  requires `b2_connected: true` and an affected-flow smoke test.
- Railway uses a persistent service model, which the background runner needs.
  The API build installs the ML stack; the weights download on the first batch
  after each deploy unless `HF_HOME` points at a mounted volume. A redeploy
  during a run leaves that batch `interrupted`.
- There is no serverless target: a Function cannot hold a resident PyTorch
  model or a background worker.
- See [infra/railway/README.md](../infra/railway/README.md) for the versioned
  configuration, approval, rollback, and cleanup procedure.
- Environment-specific configuration uses platform variables; no environment
  values are committed to the repository.
