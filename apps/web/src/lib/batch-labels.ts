import type {
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
export const MODEL_OPTIONS: { value: ModelId; label: string; description: string }[] = [
  {
    value: "ddcolor_paper_tiny",
    label: "DDColor tiny",
    description: "ConvNeXt-T, about 220 MB. Fastest; the default for CPU runs.",
  },
  {
    value: "ddcolor_modelscope",
    label: "DDColor ModelScope",
    description: "ConvNeXt-L, about 900 MB. Best overall quality.",
  },
  {
    value: "ddcolor_paper",
    label: "DDColor paper",
    description: "ConvNeXt-L, about 900 MB. The checkpoint from the ICCV 2023 paper.",
  },
  {
    value: "ddcolor_artistic",
    label: "DDColor artistic",
    description: "ConvNeXt-L, about 900 MB. More saturated, vivid colour.",
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
};

export function statusCopy(status: BatchStatus | ItemStatus) {
  return STATUS_COPY[status];
}

/** A batch can be (re-)run from any settled state. */
export function canRun(status: BatchStatus): boolean {
  return status !== "queued" && status !== "running";
}

export function runLabel(status: BatchStatus): string {
  return status === "draft" ? "Run" : "Re-run";
}

/** "3.2x" — the write-amplification ratio as the dashboard headlines it. */
export function formatRatio(ratio: number): string {
  return ratio > 0 ? `${ratio.toFixed(2)}x` : "-";
}
