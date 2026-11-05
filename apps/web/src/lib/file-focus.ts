/**
 * Focusing the Bucket Explorer on one batch's objects.
 *
 * A batch's outputs sit in three places under the app prefix
 * (`colorized/<id>/`, `comparisons/<id>/`, `manifests/<id>.csv`), so on a bucket
 * with many batches they are far from the first screen of the recent-objects
 * list. The batch page links to `/files?prefix=<a>&prefix=<b>&...`; the browser
 * then lists exactly those prefixes (not the recent page) and opens every
 * folder. `originals` names the folder holding the grayscale originals, which
 * the browser offers as an opt-in extra because that folder is shared by every
 * batch.
 */
import type { BatchDetail } from "@ddcolor-photo-colorization/shared";

export const FOCUS_PREFIX_PARAM = "prefix";
export const FOCUS_ORIGINALS_PARAM = "originals";

export interface FileFocus {
  /** Key prefixes whose objects make up the focused view. */
  prefixes: string[];
  /** Folder of the grayscale originals, when the link carried one. */
  originals: string | null;
}

function dirOf(key: string): string | null {
  const slash = key.lastIndexOf("/");
  return slash >= 0 ? key.slice(0, slash + 1) : null;
}

/** Where this batch's outputs live in B2, as `/files` focus prefixes. */
export function batchFocus(
  batch: Pick<BatchDetail, "items" | "manifest_key">,
): FileFocus {
  const prefixes: string[] = [];
  const add = (prefix: string | null) => {
    if (prefix && !prefixes.includes(prefix)) prefixes.push(prefix);
  };
  for (const item of batch.items) {
    if (item.colorized_key) add(dirOf(item.colorized_key));
    if (item.comparison_key) add(dirOf(item.comparison_key));
  }
  add(batch.manifest_key);
  const original = batch.items.find((i) => i.original_key)?.original_key;
  return { prefixes, originals: original ? dirOf(original) : null };
}

/** Link target for "View in Bucket Explorer", or `null` when there is nothing to show yet. */
export function batchFilesHref(
  batch: Pick<BatchDetail, "items" | "manifest_key">,
): string | null {
  const { prefixes, originals } = batchFocus(batch);
  if (prefixes.length === 0) return null;
  const params = new URLSearchParams();
  for (const prefix of prefixes) params.append(FOCUS_PREFIX_PARAM, prefix);
  if (originals) params.set(FOCUS_ORIGINALS_PARAM, originals);
  return `/files?${params.toString()}`;
}

/** Parse the focus from a query string; `null` when the page is not focused. */
export function focusFromSearch(search: string): FileFocus | null {
  const params = new URLSearchParams(search);
  const prefixes = params.getAll(FOCUS_PREFIX_PARAM).filter(Boolean);
  if (prefixes.length === 0) return null;
  return { prefixes, originals: params.get(FOCUS_ORIGINALS_PARAM) };
}

/** Read the focus from the current URL (client only; `null` on the server). */
export function readFocusFromUrl(): FileFocus | null {
  if (typeof window === "undefined") return null;
  return focusFromSearch(window.location.search);
}

/** Drop the focus params from the address bar, keeping any other query. */
export function clearFocusFromUrl(): void {
  if (typeof window === "undefined") return;
  const url = new URL(window.location.href);
  url.searchParams.delete(FOCUS_PREFIX_PARAM);
  url.searchParams.delete(FOCUS_ORIGINALS_PARAM);
  window.history.replaceState(null, "", `${url.pathname}${url.search}`);
}
