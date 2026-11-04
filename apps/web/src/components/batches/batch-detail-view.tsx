"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import type { BatchDetail, BatchItem } from "@ddcolor-photo-colorization/shared";
import { Download, Play, RotateCcw, Trash2 } from "lucide-react";
import { toast } from "sonner";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { BeforeAfterSlider } from "@/components/common/before-after-slider";
import { StatusBadge } from "@/components/common/status-badge";
import { EditBatchDialog } from "./edit-batch-dialog";
import { canRun, formatLabel, modelLabel, runLabel } from "@/lib/batch-labels";
import { startBrowserDownload } from "@/lib/browser-download";
import { useDeleteBatch, useManifestDownload, useRunBatch } from "@/lib/queries";
import { formatDate, humanizeBytes } from "@/lib/utils";

function ItemCard({ item }: { item: BatchItem }) {
  const name = item.original_key.split("/").pop() ?? item.original_key;
  const [showComparison, setShowComparison] = useState(false);
  return (
    <Card className="overflow-hidden">
      <div className="bg-muted">
        {item.status === "done" && item.colorized_url ? (
          showComparison && item.comparison_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={item.comparison_url} alt={`${name} comparison`} className="w-full" />
          ) : (
            <BeforeAfterSlider beforeUrl={item.original_url} afterUrl={item.colorized_url} alt={name} />
          )
        ) : (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={item.original_url} alt={name} className="w-full opacity-80" />
        )}
      </div>
      <CardContent className="space-y-1.5 p-3 text-xs">
        <div className="flex items-center justify-between gap-2">
          <span className="truncate font-medium" title={item.original_key}>
            {name}
          </span>
          <StatusBadge status={item.status} />
        </div>
        {item.width && item.height && (
          <p className="text-muted-foreground tabular-nums">
            {item.width} x {item.height}
            {item.duration_ms !== null && ` · ${(item.duration_ms / 1000).toFixed(1)} s`}
          </p>
        )}
        {item.error && <p className="text-destructive">{item.error}</p>}
        {item.comparison_url && (
          <button
            type="button"
            className="text-primary underline-offset-4 hover:underline"
            onClick={() => setShowComparison((v) => !v)}
          >
            {showComparison ? "Show slider" : "Show side-by-side"}
          </button>
        )}
      </CardContent>
    </Card>
  );
}

export function BatchDetailView({ batch }: { batch: BatchDetail }) {
  const router = useRouter();
  const run = useRunBatch();
  const remove = useDeleteBatch();
  const manifest = useManifestDownload();
  const settled = batch.done_count + batch.failed_count;
  const percent = batch.photo_count ? Math.round((settled / batch.photo_count) * 100) : 0;

  const onRun = () =>
    run.mutate(batch.batch_id, {
      onSuccess: () => toast.success("Batch queued"),
      onError: (error) =>
        toast.error(error.status === 503 ? "DDColor is not installed" : "Could not run batch", {
          description: error.message,
          duration: 12_000,
        }),
    });

  const onDelete = () =>
    remove.mutate(batch.batch_id, {
      onSuccess: (res) => {
        toast.success("Batch deleted", {
          description: `${res.deleted_objects} object(s) removed. Originals were kept.`,
        });
        router.push("/batches");
      },
      onError: (error) => toast.error("Could not delete batch", { description: error.message }),
    });

  const onManifest = () =>
    manifest.mutate(batch.batch_id, {
      onSuccess: ({ url }) => startBrowserDownload(url, `${batch.batch_id}.csv`),
      onError: (error) => toast.error("Manifest unavailable", { description: error.message }),
    });

  const facts = [
    ["Model", `${modelLabel(batch.model_id)} @ ${batch.input_size}`],
    ["Output", formatLabel(batch.output_format)],
    ["Comparisons", batch.make_comparisons ? "On" : "Off"],
    ["Originals", humanizeBytes(batch.original_bytes)],
    ["Derived", humanizeBytes(batch.derived_bytes)],
    ["Version", batch.model_version ?? "-"],
    ["Created", formatDate(batch.created_at)],
    ["Finished", batch.finished_at ? formatDate(batch.finished_at) : "-"],
  ];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4 border-b border-border pb-5">
        <div className="min-w-0 space-y-1.5">
          <div className="flex items-center gap-2">
            <h1 className="page-title truncate">{batch.name}</h1>
            <StatusBadge status={batch.status} />
          </div>
          {batch.description && (
            <p className="max-w-prose text-sm text-muted-foreground">{batch.description}</p>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          {canRun(batch.status) && (
            <Button size="sm" onClick={onRun} disabled={run.isPending}>
              {batch.status === "draft" ? (
                <Play aria-hidden className="h-3.5 w-3.5" />
              ) : (
                <RotateCcw aria-hidden className="h-3.5 w-3.5" />
              )}
              {runLabel(batch.status)}
            </Button>
          )}
          <Button size="sm" variant="outline" onClick={onManifest} disabled={!batch.manifest_key}>
            <Download aria-hidden className="h-3.5 w-3.5" />
            Manifest CSV
          </Button>
          <EditBatchDialog batch={batch} />
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button size="sm" variant="outline" disabled={!canRun(batch.status)}>
                <Trash2 aria-hidden className="h-3.5 w-3.5" />
                Delete
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Delete &quot;{batch.name}&quot;?</AlertDialogTitle>
                <AlertDialogDescription>
                  This removes the batch&apos;s colorized outputs, comparisons, manifest and record
                  from B2. The grayscale originals are kept.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Cancel</AlertDialogCancel>
                <AlertDialogAction onClick={onDelete}>Delete batch</AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </div>
      </div>

      <Card>
        <CardHeader className="border-b border-border px-5 py-4">
          <CardTitle className="card-title">Progress</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4 p-5">
          <div className="space-y-1.5">
            <Progress value={percent} aria-label="Batch progress" />
            <p className="text-xs text-muted-foreground tabular-nums">
              {batch.done_count} done · {batch.failed_count} failed · {batch.photo_count} total
            </p>
          </div>
          <dl className="grid grid-cols-2 gap-x-6 gap-y-1.5 text-sm sm:grid-cols-4">
            {facts.map(([label, value]) => (
              <div key={label} className="min-w-0">
                <dt className="text-xs text-muted-foreground">{label}</dt>
                <dd className="truncate font-medium" title={value}>
                  {value}
                </dd>
              </div>
            ))}
          </dl>
        </CardContent>
      </Card>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {batch.items.map((item) => (
          <ItemCard key={item.original_key} item={item} />
        ))}
      </div>
    </div>
  );
}
