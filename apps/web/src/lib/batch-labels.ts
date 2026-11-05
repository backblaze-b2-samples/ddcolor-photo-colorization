import type {
  Batch,
  BatchStatus,
  InputSize,
  ItemStatus,
  ModelId,
  OutputFormat,
} from "@ddcolor-photo-colorization/shared";

/**
 * Display copy for the finite batch configuration values. The values
 * themselves are generated from the API contract; only the human labels and
 * one-line descriptions live here, so the create form's selectors and the
 * read-only views always agree.
 */
export const MODEL_OPTIONS: {
  value: ModelId;
  label: string;
  description: string;
  /** Approximate checkpoint download, for the "x of about y" download text. */
  approxBytes: number;
}[] = [
  {
    value: "ddcolor_artistic",
    label: "DDColor artistic",
    description:
      "ConvNeXt-L, about 900 MB. Often the most saturated; some portraits still come out muted or sepia.",
    approxBytes: 912e6,
  },
  {
    value: "ddcolor_modelscope",
    label: "DDColor ModelScope",
    description:
      "ConvNeXt-L, about 900 MB. Upstream's demo default; worth a try when artistic looks flat.",
    approxBytes: 912e6,
  },
  {
    value: "ddcolor_paper",
    label: "DDColor paper",
    description: "ConvNeXt-L, about 900 MB. The checkpoint from the ICCV 2023 paper.",
    approxBytes: 912e6,
  },
  {
    value: "ddcolor_paper_tiny",
    label: "DDColor tiny",
    description:
      "ConvNeXt-T, about 220 MB. Fastest, but often leaves portraits and street scenes nearly gray.",
    approxBytes: 220e6,
  },
];

export const INPUT_SIZE_OPTIONS: { value: InputSize; label: string }[] = [
  { value: 256, label: "256" },
  { value: 512, label: "512" },
];

export const OUTPUT_FORMAT_OPTIONS: { value: OutputFormat; label: string }[] = [
  { value: "jpeg", label: "JPEG" },
  { value: "png", label: "PNG" },
  { value: "webp", label: "WebP" },
];

export function modelLabel(model: ModelId): string {
  return MODEL_OPTIONS.find((m) => m.value === model)?.label ?? model;
}

export function formatLabel(format: OutputFormat): string {
  return OUTPUT_FORMAT_OPTIONS.find((f) => f.value === format)?.label ?? format;
}

type Tone = "neutral" | "active" | "success" | "warning" | "danger";

const STATUS_COPY: Record<BatchStatus | ItemStatus, { label: string; tone: Tone }> = {
  draft: { label: "Draft", tone: "neutral" },
  queued: { label: "Queued", tone: "active" },
  running: { label: "Running", tone: "active" },
  pending: { label: "Pending", tone: "neutral" },
  done: { label: "Done", tone: "success" },
  partial: { label: "Partial", tone: "warning" },
  failed: { label: "Failed", tone: "danger" },
  interrupted: { label: "Interrupted", tone: "warning" },
  cancelled: { label: "Cancelled", tone: "neutral" },
};

export function statusCopy(status: BatchStatus | ItemStatus) {
  return STATUS_COPY[status];
}

/** A batch can be (re-)run from any settled state. */
export function canRun(status: BatchStatus): boolean {
  return status !== "queued" && status !== "running";
}

/**
 * The run button's label. A settled batch other than `done` keeps the photos it
 * already colorized and re-runs only the rest, so the label says so.
 */
export function runLabel(batch: Pick<Batch, "status" | "done_count" | "photo_count">): string {
  if (batch.status === "draft") return "Run";
  const unfinished = batch.photo_count - batch.done_count;
  if (batch.status !== "done" && batch.done_count > 0 && unfinished > 0) {
    return unfinished === 1 ? "Re-run 1 unfinished photo" : `Re-run ${unfinished} unfinished photos`;
  }
  return "Re-run";
}

/** The model "Colorize again with another model" suggests: the other large default. */
export function alternateModel(model: ModelId): ModelId {
  return model === "ddcolor_artistic" ? "ddcolor_modelscope" : "ddcolor_artistic";
}

const PHOTO_STEP_COPY: Partial<Record<NonNullable<Batch["stage"]>, string>> = {
  reading_photo: "reading the original from B2",
  colorizing_photo: "colorizing",
  saving_result: "saving the result to B2",
};

/**
 * What a running batch is doing right now: the current photo, its position and
 * its step ("Colorizing x.jpg (2 of 4): saving the result to B2..."), so a slow
 * photo never looks frozen. Null outside the running state.
 */
export function runningStageText(
  batch: Pick<Batch, "status" | "stage"> & {
    items: readonly { original_key: string; status: ItemStatus }[];
  },
): string | null {
  if (batch.status !== "running") return null;
  if (batch.stage === "saving_manifest") return "Writing the manifest CSV to B2...";
  const index = batch.items.findIndex((i) => i.status === "running");
  if (index < 0) return "Starting the next photo...";
  const name = batch.items[index].original_key.split("/").pop();
  const step = (batch.stage && PHOTO_STEP_COPY[batch.stage]) ?? "colorizing";
  return `Photo ${index + 1} of ${batch.items.length}, ${name}: ${step}...`;
}

/**
 * What a queued batch is waiting on, in words: the model download (with bytes
 * so far), the model load, or the worker itself. Null once the batch runs.
 */
export function queuedStageText(
  batch: Pick<Batch, "status" | "stage" | "model_download_bytes" | "model_id">,
): string | null {
  if (batch.status !== "queued") return null;
  const model = MODEL_OPTIONS.find((m) => m.value === batch.model_id);
  const label = model?.label ?? batch.model_id;
  if (batch.stage === "downloading_model") {
    const mb = Math.round((batch.model_download_bytes ?? 0) / 1e6);
    const total = model ? ` of about ${Math.round(model.approxBytes / 1e6)} MB` : "";
    return `Downloading ${label} weights from the Hugging Face Hub: ${mb} MB${total}. First use only.`;
  }
  if (batch.stage === "loading_model") return `Loading ${label} into memory...`;
  if (batch.stage === "preparing_model") return `Preparing ${label}...`;
  return "Waiting for the colorization worker (another batch may be running).";
}

/**
 * Percent of the model download so far (bytes in the Hub cache over the
 * checkpoint's approximate size, capped at 99 until the load stage begins),
 * or null outside the download stage.
 */
export function modelDownloadPercent(
  batch: Pick<Batch, "status" | "stage" | "model_download_bytes" | "model_id">,
): number | null {
  if (batch.status !== "queued" || batch.stage !== "downloading_model") return null;
  const model = MODEL_OPTIONS.find((m) => m.value === batch.model_id);
  if (!model) return null;
  const pct = Math.round(((batch.model_download_bytes ?? 0) / model.approxBytes) * 100);
  return Math.min(99, Math.max(0, pct));
}

/** "3.2x" — the write-amplification ratio as the dashboard headlines it. */
export function formatRatio(ratio: number): string {
  return ratio > 0 ? `${ratio.toFixed(2)}x` : "-";
}
