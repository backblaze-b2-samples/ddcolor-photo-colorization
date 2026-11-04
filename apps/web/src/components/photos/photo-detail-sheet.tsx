"use client";

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

/** Before/after slider for the latest version plus every version across batches. */
export function PhotoDetailSheet({ photoKey, onOpenChange }: PhotoDetailSheetProps) {
  const { data: photo, isLoading, error, refetch } = usePhotoDetail(photoKey);
  const latest = photo?.versions[0];

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
          ) : photo && latest ? (
            <BeforeAfterSlider
              beforeUrl={photo.original_url}
              afterUrl={latest.colorized_url}
              alt={photo.filename}
            />
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
                {photo.versions.map((v) => (
                  <li key={v.colorized_key} className="flex items-center gap-3 p-3 text-sm">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={v.colorized_url} alt="" className="h-12 w-16 rounded object-cover" />
                    <div className="min-w-0 flex-1">
                      <Link
                        href={`/batches/${v.batch_id}`}
                        className="block truncate font-medium underline-offset-4 hover:underline"
                      >
                        {v.batch_name}
                      </Link>
                      <p className="text-xs text-muted-foreground">
                        {modelLabel(v.model_id)} @ {v.input_size} · {humanizeBytes(v.size)}
                        {v.processed_at && ` · ${formatDate(v.processed_at)}`}
                      </p>
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
                ))}
              </ul>
            </div>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}
