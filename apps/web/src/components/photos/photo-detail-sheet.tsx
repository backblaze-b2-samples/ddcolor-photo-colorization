"use client";

import { useState } from "react";
import Link from "next/link";
import { Download } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/ui/error-state";
import { BeforeAfterSlider } from "@/components/common/before-after-slider";
import { modelLabel } from "@/lib/batch-labels";
import { startBrowserDownload } from "@/lib/browser-download";
import { usePhotoDetail } from "@/lib/queries";
import { formatDate, humanizeBytes } from "@/lib/utils";

interface PhotoDetailSheetProps {
  photoKey: string | undefined;
  onOpenChange: (open: boolean) => void;
}

/**
 * Before/after slider plus every version across batches. The slider shows the
 * latest version until the user picks another row; the label names its model.
 */
export function PhotoDetailSheet({ photoKey, onOpenChange }: PhotoDetailSheetProps) {
  const { data: photo, isLoading, error, refetch } = usePhotoDetail(photoKey);
  // Keyed by photo, so opening another photo falls back to its latest version.
  const [picked, setPicked] = useState<{ photo: string; version: string } | null>(null);
  const pickedKey = picked && picked.photo === photoKey ? picked.version : undefined;
  const shown =
    photo?.versions.find((v) => v.colorized_key === pickedKey) ?? photo?.versions[0];
  const show = (version: string) => photoKey && setPicked({ photo: photoKey, version });

  return (
    <Sheet open={!!photoKey} onOpenChange={onOpenChange}>
      <SheetContent className="w-full overflow-y-auto sm:max-w-xl">
        <SheetHeader>
          <SheetTitle className="truncate">{photo?.filename ?? "Photo"}</SheetTitle>
          <SheetDescription>
            {photo
              ? `${humanizeBytes(photo.size)} original · ingested ${formatDate(photo.last_modified)}${
                  photo.was_color ? " · was already colour (desaturated before inference)" : ""
                }`
              : "Loading..."}
          </SheetDescription>
        </SheetHeader>
        <div className="space-y-5 px-4 pb-6">
          {isLoading ? (
            <Skeleton className="aspect-[4/3] w-full" />
          ) : error ? (
            <ErrorState error={error} onRetry={() => refetch()} />
          ) : photo && shown ? (
            <div className="space-y-1.5">
              <BeforeAfterSlider
                beforeUrl={photo.original_url}
                afterUrl={shown.colorized_url}
                alt={photo.filename}
                afterLabel={modelLabel(shown.model_id)}
              />
              <p className="text-xs text-muted-foreground" aria-live="polite">
                Showing {modelLabel(shown.model_id)} @ {shown.input_size} from{" "}
                <span className="font-medium text-foreground">{shown.batch_name}</span>
                {shown === photo.versions[0] ? " (latest)" : ""}
                {photo.versions.length > 1 ? ". Choose a version below to compare it." : "."}
              </p>
            </div>
          ) : photo ? (
            <>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={photo.original_url} alt={photo.filename} className="w-full rounded-md" />
              <p className="text-sm text-muted-foreground">
                Not colorized yet. Select it in the library and choose Colorize selected.
              </p>
            </>
          ) : null}

          {photo && photo.versions.length > 0 && (
            <div className="space-y-2">
              <h3 className="text-sm font-semibold">
                Colorized versions ({photo.versions.length})
              </h3>
              <ul className="divide-y divide-border rounded-md border border-border">
                {photo.versions.map((v) => {
                  const isShown = v.colorized_key === shown?.colorized_key;
                  return (
                    <li
                      key={v.colorized_key}
                      className={`flex items-center gap-3 p-3 text-sm ${isShown ? "bg-muted" : ""}`}
                    >
                      <button
                        type="button"
                        onClick={() => show(v.colorized_key)}
                        aria-pressed={isShown}
                        aria-label={`Show ${modelLabel(v.model_id)} from ${v.batch_name} in the slider`}
                        className={`shrink-0 rounded ring-offset-2 ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                          isShown ? "ring-2 ring-primary" : "hover:opacity-80"
                        }`}
                      >
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img src={v.colorized_url} alt="" className="h-12 w-16 rounded object-cover" />
                      </button>
                      <div className="min-w-0 flex-1">
                        <Link
                          href={`/batches/${v.batch_id}`}
                          className="block truncate font-medium underline-offset-4 hover:underline"
                        >
                          {v.batch_name}
                        </Link>
                        <button
                          type="button"
                          onClick={() => show(v.colorized_key)}
                          className="block text-left text-xs text-muted-foreground hover:text-foreground"
                        >
                          {modelLabel(v.model_id)} @ {v.input_size} · {humanizeBytes(v.size)}
                          {v.processed_at && ` · ${formatDate(v.processed_at)}`}
                        </button>
                      </div>
                      <Button
                        size="sm"
                        variant="outline"
                        aria-label={`Download version from ${v.batch_name}`}
                        onClick={() => startBrowserDownload(v.download_url)}
                      >
                        <Download aria-hidden className="h-3.5 w-3.5" />
                      </Button>
                    </li>
                  );
                })}
              </ul>
            </div>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}
