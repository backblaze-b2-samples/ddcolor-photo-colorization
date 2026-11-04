import type { BatchStatus, ItemStatus } from "@ddcolor-photo-colorization/shared";
import { Loader2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { statusCopy } from "@/lib/batch-labels";
import { cn } from "@/lib/utils";

const TONE_CLASS = {
  neutral: "bg-muted text-muted-foreground",
  active: "bg-primary/10 text-primary",
  success: "bg-[var(--success)]/15 text-[var(--success)]",
  warning: "bg-amber-500/15 text-amber-600 dark:text-amber-400",
  danger: "bg-destructive/15 text-destructive",
} as const;

export function StatusBadge({ status }: { status: BatchStatus | ItemStatus }) {
  const { label, tone } = statusCopy(status);
  const spinning = status === "running" || status === "queued";
  return (
    <Badge variant="secondary" className={cn("gap-1", TONE_CLASS[tone])}>
      {spinning && <Loader2 aria-hidden className="animate-spin motion-reduce:animate-none" />}
      {label}
    </Badge>
  );
}
