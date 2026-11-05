import { describe, expect, it } from "vitest";
import type { BatchItem } from "@ddcolor-photo-colorization/shared";

import { batchFilesHref, batchFocus, focusFromSearch } from "./file-focus";

function item(name: string, batchId: string, done = true): BatchItem {
  return {
    original_key: `colorization/grayscale/${name}.jpg`,
    colorized_key: done ? `colorization/colorized/${batchId}/${name}.jpg` : null,
    comparison_key: done ? `colorization/comparisons/${batchId}/${name}.jpg` : null,
  } as BatchItem;
}

const ID = "b-20261104-101500-abc123";
const batch = {
  items: [item("a", ID), item("b", ID)],
  manifest_key: `colorization/manifests/${ID}.csv`,
};

describe("batchFocus", () => {
  it("lists the colorized folder, comparisons folder and manifest once each", () => {
    expect(batchFocus(batch)).toEqual({
      prefixes: [
        `colorization/colorized/${ID}/`,
        `colorization/comparisons/${ID}/`,
        `colorization/manifests/${ID}.csv`,
      ],
      originals: "colorization/grayscale/",
    });
  });

  it("has nothing to show before any output exists", () => {
    expect(batchFilesHref({ items: [item("a", ID, false)], manifest_key: null })).toBeNull();
  });
});

describe("batchFilesHref / focusFromSearch", () => {
  it("round-trips through the query string", () => {
    const href = batchFilesHref(batch)!;
    expect(href.startsWith("/files?")).toBe(true);
    expect(focusFromSearch(href.slice(href.indexOf("?")))).toEqual(batchFocus(batch));
  });

  it("is not a focus without prefix params", () => {
    expect(focusFromSearch("?preview=x")).toBeNull();
    expect(focusFromSearch("")).toBeNull();
  });
});
