import { describe, expect, it } from "vitest";

import {
  MODEL_OPTIONS,
  canRun,
  formatRatio,
  modelLabel,
  runLabel,
  statusCopy,
} from "./batch-labels";
import { isBatchActive } from "./queries";

describe("batch labels", () => {
  it("offers every DDColor checkpoint with the tiny model first (the CPU default)", () => {
    expect(MODEL_OPTIONS.map((m) => m.value)).toEqual([
      "ddcolor_paper_tiny",
      "ddcolor_modelscope",
      "ddcolor_paper",
      "ddcolor_artistic",
    ]);
    expect(modelLabel("ddcolor_artistic")).toBe("DDColor artistic");
  });

  it("only lets settled batches run, and names the action by state", () => {
    expect(canRun("draft")).toBe(true);
    expect(canRun("interrupted")).toBe(true);
    expect(canRun("running")).toBe(false);
    expect(canRun("queued")).toBe(false);
    expect(runLabel("draft")).toBe("Run");
    expect(runLabel("partial")).toBe("Re-run");
  });

  it("polls only while the worker is still changing a batch", () => {
    expect(isBatchActive("running")).toBe(true);
    expect(isBatchActive("queued")).toBe(true);
    expect(isBatchActive("done")).toBe(false);
    expect(isBatchActive(undefined)).toBe(false);
  });

  it("formats status and ratio copy", () => {
    expect(statusCopy("partial")).toEqual({ label: "Partial", tone: "warning" });
    expect(formatRatio(3.14159)).toBe("3.14x");
    expect(formatRatio(0)).toBe("-");
  });
});
