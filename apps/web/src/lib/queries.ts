"use client";

import {
  useMutation,
  useQueries,
  useQuery,
  useQueryClient,
  type QueryClient,
} from "@tanstack/react-query";
import {
  ApiError,
  cancelBatch,
  createBatch,
  deleteBatch,
  deleteFile,
  getBatch,
  getBatches,
  getBatchStats,
  getManifestDownloadUrl,
  getPhotoDetail,
  getPhotos,
  getDownloadUrl,
  getFileDetail,
  getFiles,
  getFileStats,
  getHealth,
  getPreviewUrl,
  getUploadActivity,
  runBatch,
  updateBatch,
} from "@/lib/api-client";
import type {
  Batch,
  BatchDetail,
  BatchStatus,
  CreateBatchRequest,
  UpdateBatchRequest,
  FileMetadata,
  FileMetadataDetail,
  FileUrlResponse,
} from "@ddcolor-photo-colorization/shared";
import { qk } from "@/lib/generated/query-keys";
import { FOCUS_LIST_LIMIT } from "@/lib/file-list-limit";

// Query keys are GENERATED from the API contract (`pnpm gen:api`) and their
// hierarchy is declared in `scripts/gen/api-gen.config.json`, so invalidating
// a parent key still reaches its children and no hook can invent a key the API
// cannot answer. Re-exported here because this module is the data layer's
// public surface: components and tests import `qk` from `@/lib/queries`.
//
// The caching policy below — staleTime, refetchInterval, retry, `enabled`
// gating, the query-vs-mutation choice, and the cache surgery in
// `dropDeletedFileFromCache` — is hand-written on purpose and is never
// generated.
export { qk };

export type Health = Awaited<ReturnType<typeof getHealth>>;

/**
 * Gate a query on something being open/visible. Deliberately the only option we
 * expose, so callers can't drift the caching policy per call site — the ⌘K
 * palette reuses `useFiles`' key (and therefore its cache) instead of fetching
 * its own private, smaller list.
 */
export interface QueryGate {
  enabled?: boolean;
}

export function useFiles(prefix = "", limit = 100, { enabled = true }: QueryGate = {}) {
  return useQuery<FileMetadata[], ApiError>({
    queryKey: qk.files(prefix, limit),
    queryFn: () => getFiles(prefix, limit),
    enabled,
  });
}

/**
 * The first `pageCount` newest-first pages of the bucket listing, merged.
 *
 * Page 0 shares `useFiles`' cache entry (same key), and every page is an
 * ordinary array query under the `files` key, so the delete cache surgery and
 * the post-upload invalidation reach all of them. "Load more" is just
 * `pageCount + 1`. Rows are de-duplicated by key because an upload between two
 * page fetches shifts the offsets by one.
 */
export function useFilePages(prefix: string, pageSize: number, pageCount: number) {
  const { results, files } = useQueries({
    queries: Array.from({ length: pageCount }, (_, page) => ({
      queryKey: qk.files(prefix, pageSize, page * pageSize),
      queryFn: () => getFiles(prefix, pageSize, page * pageSize),
    })),
    // `combine` output is structurally shared, so `files` keeps its identity
    // between renders while no page changed (the tree and effects key on it).
    combine: (queryResults) => {
      const seen = new Set<string>();
      const merged: FileMetadata[] = [];
      for (const result of queryResults) {
        for (const file of result.data ?? []) {
          if (seen.has(file.key)) continue;
          seen.add(file.key);
          merged.push(file);
        }
      }
      return { results: queryResults, files: merged };
    },
  });
  const first = results[0];
  const last = results[results.length - 1];
  return {
    files,
    isLoading: first.isLoading,
    isFetching: results.some((r) => r.isFetching),
    // A failure on a later page must not blank the pages already on screen.
    error: first.error as ApiError | null,
    loadMoreError: pageCount > 1 ? (last.error as ApiError | null) : null,
    /** The last page came back full, so another one may exist. */
    hasMore: last.data !== undefined && last.data.length >= pageSize,
    isLoadingMore: pageCount > 1 && last.isLoading,
    refetch: () => Promise.all(results.map((r) => r.refetch())),
  };
}

/**
 * Every object (up to the API's 1000-row page) under each of `prefixes`,
 * merged and de-duplicated. Backs the Bucket Explorer's focused view: unlike the
 * recent-objects pages these are exact prefix listings, so an object is
 * reachable however old it is. Disabled while `prefixes` is empty.
 */
export function useFilesByPrefixes(prefixes: string[]) {
  return useQueries({
    queries: prefixes.map((prefix) => ({
      queryKey: qk.files(prefix, FOCUS_LIST_LIMIT, 0),
      queryFn: () => getFiles(prefix, FOCUS_LIST_LIMIT, 0),
    })),
    combine: (results) => {
      const seen = new Set<string>();
      const files: FileMetadata[] = [];
      for (const result of results) {
        for (const file of result.data ?? []) {
          if (seen.has(file.key)) continue;
          seen.add(file.key);
          files.push(file);
        }
      }
      return {
        files,
        isLoading: results.some((r) => r.isLoading),
        isFetching: results.some((r) => r.isFetching),
        error: (results.find((r) => r.error)?.error ?? null) as ApiError | null,
        refetch: () => Promise.all(results.map((r) => r.refetch())),
      };
    },
  });
}

export function useFileStats({ enabled = true }: QueryGate = {}) {
  return useQuery({
    queryKey: qk.stats(),
    queryFn: getFileStats,
    enabled,
  });
}

export function useUploadActivity(days = 7) {
  return useQuery({
    queryKey: qk.uploadActivity(days),
    queryFn: () => getUploadActivity(days),
  });
}

// Presigned preview URL — only fetched when `enabled` is true (e.g., when
// the dialog opens for a specific file). Kept short-lived (60s) because
// the URL itself has a presigned expiry and is cheap to regenerate.
export function usePreviewUrl(key: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: qk.preview(key ?? ""),
    queryFn: () => getPreviewUrl(key as string),
    enabled: enabled && !!key,
    staleTime: 60_000,
  });
}

// Rich metadata for an already-stored file. The server recomputes it on demand
// (a full object download), so it's only fetched when `enabled` — i.e. the
// preview dialog is open AND the user expands "Detailed metadata". Kept
// short-lived like the preview URL; cheap correctness under key overwrites.
export function useFileDetail(key: string | undefined, enabled: boolean) {
  return useQuery<FileMetadataDetail, ApiError>({
    queryKey: qk.detail(key ?? ""),
    queryFn: () => getFileDetail(key as string),
    enabled: enabled && !!key,
    staleTime: 60_000,
  });
}

// Health poll for the top-of-app B2 banner. `retry: false` and letting a
// failed fetch leave `data` undefined keeps a down API silent (the
// per-component ErrorState covers that); the banner only reacts to an up API
// reporting b2_connected: false. Polls every 60s and on window focus.
export function useHealth() {
  return useQuery<Health>({
    queryKey: qk.health(),
    queryFn: getHealth,
    refetchInterval: 60_000,
    staleTime: 30_000,
    retry: false,
  });
}

/**
 * Drop a deleted object from every cached file list, plus its own cached
 * preview/detail entries.
 *
 * Invalidation alone is not enough: the refetch re-lists the whole bucket and
 * took 5-6s in practice, so the success toast fired while the row was still
 * listed — and using that stale row's Preview 404'd. Editing the cache makes
 * the row disappear with the toast; the invalidation that follows still
 * reconciles against the server.
 *
 * Exported for tests — the mutation below is its only production caller.
 */
export function dropDeletedFileFromCache(qc: QueryClient, fileKey: string) {
  qc.setQueriesData<FileMetadata[]>(
    // Partial key: matches qk.files(prefix, limit) for every prefix/limit.
    { queryKey: [...qk.all, "files"] },
    (previous) =>
      previous ? previous.filter((file) => file.key !== fileKey) : previous,
  );
  // A presigned URL for a deleted key can only 404 now.
  qc.removeQueries({ queryKey: qk.preview(fileKey) });
  qc.removeQueries({ queryKey: qk.detail(fileKey) });
}

/**
 * Fetch a download URL for one file.
 *
 * A mutation, not a query: it has a server side effect (it bumps the download
 * counter) and it must never be cached or replayed. Being a mutation is also
 * what gives the UI an honest pending state — the old code awaited the presign
 * inside a plain click handler, so a slow round trip left the screen completely
 * unchanged and a user could not tell a working download from a dead button.
 *
 * The caller performs the navigation (see `lib/browser-download.ts`) and gets
 * `isPending` / `variables` for the pending row.
 */
export function useDownloadUrl() {
  const qc = useQueryClient();
  return useMutation<FileUrlResponse, ApiError, FileMetadata>({
    mutationFn: (file) => getDownloadUrl(file.key),
    // The server counted a download, so the dashboard's "Total Downloads" is
    // now stale. Cheap: /files/stats reads a cached bucket listing.
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.stats() }),
  });
}

export function useDeleteFile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (fileKey: string) => deleteFile(fileKey),
    onSuccess: (_data, fileKey) => {
      // Remove the row immediately, then reconcile everything (lists, stats,
      // activity) against the server in the background.
      dropDeletedFileFromCache(qc, fileKey);
      qc.invalidateQueries({ queryKey: qk.all });
    },
  });
}

// --- Colorization batches -------------------------------------------------

/** Statuses during which the background worker is still changing a batch. */
export const ACTIVE_BATCH_STATUSES: readonly BatchStatus[] = ["queued", "running"];

export function isBatchActive(status: BatchStatus | undefined): boolean {
  return status !== undefined && ACTIVE_BATCH_STATUSES.includes(status);
}

/** Poll interval while a batch is queued or running; off once it settles. */
export const BATCH_POLL_MS = 2_000;

/** Detail keys append the id to the generated parent key, so invalidating
 *  `[...qk.all, "batches"]` reaches lists, stats and every detail. */
export function batchDetailKey(batchId: string) {
  return [...qk.batch(), batchId] as const;
}

export function useBatches(limit = 50) {
  return useQuery<Batch[], ApiError>({
    queryKey: qk.batches(limit),
    queryFn: () => getBatches(limit),
    // Keep the list live while anything in it is still running.
    refetchInterval: (query) =>
      query.state.data?.some((b) => isBatchActive(b.status)) ? BATCH_POLL_MS : false,
  });
}

export function useBatch(batchId: string) {
  return useQuery<BatchDetail, ApiError>({
    queryKey: batchDetailKey(batchId),
    queryFn: () => getBatch(batchId),
    enabled: batchId.length > 0,
    refetchInterval: (query) =>
      isBatchActive(query.state.data?.status) ? BATCH_POLL_MS : false,
    // Presigned gallery URLs last an hour; refetching sooner is wasted signing.
    staleTime: 30_000,
  });
}

export function useBatchStats() {
  return useQuery({
    queryKey: qk.batchStats(),
    queryFn: getBatchStats,
    refetchInterval: (query) =>
      query.state.data?.recent_batches.some((b) => isBatchActive(b.status))
        ? BATCH_POLL_MS * 2
        : false,
  });
}

function invalidateColorization(qc: QueryClient) {
  qc.invalidateQueries({ queryKey: [...qk.all, "batches"] });
  qc.invalidateQueries({ queryKey: [...qk.all, "photos"] });
  // Derived objects land in the bucket too, so the explorer and its stats move.
  qc.invalidateQueries({ queryKey: [...qk.all, "files"] });
  qc.invalidateQueries({ queryKey: qk.stats() });
}

export function useCreateBatch() {
  const qc = useQueryClient();
  return useMutation<Batch, ApiError, CreateBatchRequest>({
    mutationFn: createBatch,
    onSuccess: () => invalidateColorization(qc),
  });
}

export function useUpdateBatch(batchId: string) {
  const qc = useQueryClient();
  return useMutation<Batch, ApiError, UpdateBatchRequest>({
    mutationFn: (body) => updateBatch(batchId, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: [...qk.all, "batches"] }),
  });
}

export function useDeleteBatch() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (batchId: string) => deleteBatch(batchId),
    onSuccess: (_data, batchId) => {
      qc.removeQueries({ queryKey: batchDetailKey(batchId) });
      invalidateColorization(qc);
    },
  });
}

/**
 * Show a batch's new status the moment the user acts: patch the cached detail
 * optimistically, roll back on error, and write the server's answer on success
 * (then refetch everything that depends on it).
 */
function statusMutation(
  qc: QueryClient,
  mutationFn: (batchId: string) => Promise<Batch>,
  optimistic: BatchStatus,
) {
  return {
    mutationFn,
    onMutate: async (batchId: string) => {
      const key = batchDetailKey(batchId);
      await qc.cancelQueries({ queryKey: key });
      const previous = qc.getQueryData<BatchDetail>(key);
      if (previous) qc.setQueryData<BatchDetail>(key, { ...previous, status: optimistic, stage: null });
      return { previous };
    },
    onError: (_error: ApiError, batchId: string, context?: { previous?: BatchDetail }) => {
      if (context?.previous) qc.setQueryData(batchDetailKey(batchId), context.previous);
    },
    onSuccess: (batch: Batch) => {
      qc.setQueryData<BatchDetail>(batchDetailKey(batch.batch_id), (old) =>
        old ? { ...old, ...batch } : old,
      );
      invalidateColorization(qc);
    },
  };
}

export function useRunBatch() {
  const qc = useQueryClient();
  return useMutation<Batch, ApiError, string, { previous?: BatchDetail }>(
    statusMutation(qc, runBatch, "queued"),
  );
}

export function useCancelBatch() {
  const qc = useQueryClient();
  return useMutation<Batch, ApiError, string, { previous?: BatchDetail }>(
    statusMutation(qc, cancelBatch, "cancelled"),
  );
}

/** A mutation, like file downloads: a fresh presigned URL per click, never cached. */
export function useManifestDownload() {
  return useMutation<FileUrlResponse, ApiError, string>({
    mutationFn: getManifestDownloadUrl,
  });
}

// --- Photo Library ----------------------------------------------------------

export function usePhotos(limit = 48, cursor?: string) {
  return useQuery({
    queryKey: qk.photos(limit, cursor),
    queryFn: () => getPhotos(limit, cursor),
    staleTime: 30_000,
  });
}

export function usePhotoDetail(key: string | undefined) {
  return useQuery({
    queryKey: qk.photoDetail(key ?? ""),
    queryFn: () => getPhotoDetail(key as string),
    enabled: !!key,
    staleTime: 30_000,
  });
}
