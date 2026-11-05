import { describe, expect, it } from "vitest";

import {
  MODEL_OPTIONS,
  canRun,
  formatRatio,
  modelDownloadPercent,
  modelLabel,
  queuedStageText,
  runLabel,
  runningStageText,
  alternateModel,
  statusCopy,
} from "./batch-labels";
import { isBatchActive } from "./queries";

describe("batch labels", () => {
  it("offers every DDColor checkpoint with the artistic model (the default) first", () => {
    expect(MODEL_OPTIONS.map((m) => m.value)).toEqual([
      "ddcolor_artistic",
      "ddcolor_modelscope",
      "ddcolor_paper",
      "ddcolor_paper_tiny",
    ]);
    expect(modelLabel("ddcolor_artistic")).toBe("DDColor artistic");
  });

  it("only lets settled batches run, and names the action by state", () => {
    expect(canRun("draft")).toBe(true);
    expect(canRun("interrupted")).toBe(true);
    expect(canRun("cancelled")).toBe(true);
    expect(canRun("running")).toBe(false);
    expect(canRun("queued")).toBe(false);
    const counts = { photo_count: 4, done_count: 0 };
    expect(runLabel({ ...counts, status: "draft" })).toBe("Run");
    expect(runLabel({ ...counts, status: "failed" })).toBe("Re-run");
    expect(runLabel({ photo_count: 4, done_count: 3, status: "partial" })).toBe(
      "Re-run 1 unfinished photo",
    );
    expect(runLabel({ photo_count: 4, done_count: 1, status: "cancelled" })).toBe(
      "Re-run 3 unfinished photos",
    );
    expect(runLabel({ photo_count: 4, done_count: 4, status: "done" })).toBe("Re-run");
    expect(alternateModel("ddcolor_artistic")).toBe("ddcolor_modelscope");
    expect(alternateModel("ddcolor_paper_tiny")).toBe("ddcolor_artistic");
  });

  it("polls only while the worker is still changing a batch", () => {
    expect(isBatchActive("running")).toBe(true);
    expect(isBatchActive("queued")).toBe(true);
    expect(isBatchActive("done")).toBe(false);
    expect(isBatchActive(undefined)).toBe(false);
  });

  it("names what a queued batch is waiting on", () => {
    const base = { model_id: "ddcolor_artistic" as const, model_download_bytes: null };
    expect(
      queuedStageText({ ...base, status: "queued", stage: "downloading_model", model_download_bytes: 412e6 }),
    ).toBe(
      "Downloading DDColor artistic weights from the Hugging Face Hub: 412 MB of about 912 MB. First use only.",
    );
    expect(queuedStageText({ ...base, status: "queued", stage: "loading_model" })).toBe(
      "Loading DDColor artistic into memory...",
    );
    expect(queuedStageText({ ...base, status: "queued", stage: null })).toBe(
      "Waiting for the colorization worker (another batch may be running).",
    );
    expect(queuedStageText({ ...base, status: "queued", stage: "preparing_model" })).toBe(
      "Preparing DDColor artistic...",
    );
    expect(queuedStageText({ ...base, status: "running", stage: null })).toBeNull();
  });

  it("names the running photo and its step", () => {
    const items = [
      { original_key: "colorization/grayscale/a.jpg", status: "done" as const },
      { original_key: "colorization/grayscale/b.jpg", status: "running" as const },
      { original_key: "colorization/grayscale/c.jpg", status: "pending" as const },
    ];
    expect(runningStageText({ status: "running", stage: "saving_result", items })).toBe(
      "Photo 2 of 3, b.jpg: saving the result to B2...",
    );
    expect(runningStageText({ status: "running", stage: "saving_manifest", items })).toBe(
      "Writing the manifest CSV to B2...",
    );
    expect(runningStageText({ status: "queued", stage: null, items })).toBeNull();
  });

  it("turns the model download into a determinate percent", () => {
    const base = { model_id: "ddcolor_artistic" as const, status: "queued" as const };
    expect(
      modelDownloadPercent({ ...base, stage: "downloading_model", model_download_bytes: 456e6 }),
    ).toBe(50);
    expect(
      modelDownloadPercent({ ...base, stage: "downloading_model", model_download_bytes: null }),
    ).toBe(0);
    expect(
      modelDownloadPercent({ ...base, stage: "downloading_model", model_download_bytes: 2e9 }),
    ).toBe(99);
    expect(modelDownloadPercent({ ...base, stage: "loading_model", model_download_bytes: 9e8 })).toBeNull();
  });

  it("formats status and ratio copy", () => {
    expect(statusCopy("partial")).toEqual({ label: "Partial", tone: "warning" });
    expect(formatRatio(3.14159)).toBe("3.14x");
    expect(formatRatio(0)).toBe("-");
  });
});
