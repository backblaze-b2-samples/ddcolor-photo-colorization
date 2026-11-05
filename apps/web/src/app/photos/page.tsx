"use client";

import { useState } from "react";
import Link from "next/link";
import { ImageIcon, Palette, Upload } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { Skeleton } from "@/components/ui/skeleton";
import { CreateBatchDialog } from "@/components/batches/create-batch-dialog";
import { LoadingImage } from "@/components/common/loading-image";
import { PhotoDetailSheet } from "@/components/photos/photo-detail-sheet";
import { modelLabel } from "@/lib/batch-labels";
import { usePhotos } from "@/lib/queries";

const PAGE_SIZE = 48;

export default function PhotosPage() {
  const [cursors, setCursors] = useState<(string | undefined)[]>([undefined]);
  const cursor = cursors[cursors.length - 1];
  const { data, isLoading, error, refetch } = usePhotos(PAGE_SIZE, cursor);
  const [selected, setSelected] = useState<string[]>([]);
  const [openKey, setOpenKey] = useState<string | undefined>();

  const toggle = (key: string, on: boolean) =>
    setSelected((prev) => (on ? [...prev, key] : prev.filter((k) => k !== key)));
  const pageKeys = data?.items.map((p) => p.key) ?? [];
  const uncolorizedKeys = data?.items.filter((p) => p.colorized_versions === 0).map((p) => p.key) ?? [];
  const allOnPageSelected = pageKeys.length > 0 && pageKeys.every((k) => selected.includes(k));
  const selectKeys = (keys: string[]) =>
    setSelected((prev) => [...prev, ...keys.filter((k) => !prev.includes(k))]);

  return (
    <div className="space-y-8">
      <div className="animate-fade-in flex flex-wrap items-start justify-between gap-4 border-b border-border pb-5">
        <div>
          <h1 className="page-title">Photo Library</h1>
          <p className="mt-1.5 max-w-prose text-sm text-muted-foreground">
            Grayscale originals under <code>colorization/grayscale/</code>, each with its latest
            colorized version. Open a photo for a before/after view of every version.
          </p>
        </div>
        <div className="flex gap-2">
          <Button asChild size="sm" variant="outline" className="h-8">
            <Link href="/upload">
              <Upload aria-hidden className="h-3.5 w-3.5" />
              Ingest photos
            </Link>
          </Button>
          <CreateBatchDialog
            presetKeys={selected}
            trigger={
              <Button size="sm" className="h-8" disabled={selected.length === 0}>
                <Palette aria-hidden className="h-3.5 w-3.5" />
                Colorize selected{selected.length > 0 ? ` (${selected.length})` : ""}
              </Button>
            }
          />
        </div>
      </div>

      {isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <Skeleton key={i} className="aspect-[4/3] w-full" />
          ))}
        </div>
      ) : error ? (
        <ErrorState error={error} onRetry={() => refetch()} />
      ) : !data || data.items.length === 0 ? (
        <EmptyState
          icon={ImageIcon}
          title="No photos yet"
          description="Ingest black-and-white scans, or run pnpm seed:demo for eight public-domain photos."
        />
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <label className="flex cursor-pointer items-center gap-2">
              <Checkbox
                checked={allOnPageSelected}
                onCheckedChange={(on) =>
                  on === true
                    ? selectKeys(pageKeys)
                    : setSelected((prev) => prev.filter((k) => !pageKeys.includes(k)))
                }
                aria-label="Select all photos on this page"
              />
              Select all on this page
            </label>
            <Button
              size="sm"
              variant="ghost"
              className="h-8"
              disabled={uncolorizedKeys.length === 0}
              onClick={() => selectKeys(uncolorizedKeys)}
            >
              Select not yet colorized ({uncolorizedKeys.length})
            </Button>
            {selected.length > 0 && (
              <Button size="sm" variant="ghost" className="h-8" onClick={() => setSelected([])}>
                Clear selection
              </Button>
            )}
          </div>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {data.items.map((photo) => {
              const checked = selected.includes(photo.key);
              return (
                <Card key={photo.key} className="group relative overflow-hidden p-0">
                  <button
                    type="button"
                    onClick={() => setOpenKey(photo.key)}
                    className="relative block aspect-[4/3] w-full overflow-hidden bg-muted"
                    aria-label={`Open ${photo.filename}`}
                  >
                    <LoadingImage
                      src={photo.colorized_url ?? photo.original_url}
                      alt={photo.filename}
                      loading="lazy"
                      className="h-full w-full object-cover transition-transform group-hover:scale-[1.02]"
                    />
                    {/* Names the version the thumbnail shows: the latest. */}
                    {photo.colorized_model_id && (
                      <span className="pointer-events-none absolute bottom-2 right-2 rounded bg-black/60 px-1.5 py-0.5 text-[11px] font-medium text-white">
                        {modelLabel(photo.colorized_model_id)}
                      </span>
                    )}
                  </button>
                  <label className="absolute left-2 top-2 flex items-center rounded bg-background/90 p-1 shadow">
                    <Checkbox
                      checked={checked}
                      onCheckedChange={(on) => toggle(photo.key, on === true)}
                      aria-label={`Select ${photo.filename}`}
                    />
                  </label>
                  <div className="flex items-center justify-between gap-2 px-3 py-2 text-xs">
                    <span className="truncate font-medium" title={photo.key}>
                      {photo.filename}
                    </span>
                    <span className="flex shrink-0 gap-1">
                      {photo.was_color && <Badge variant="outline">was color</Badge>}
                      <Badge variant="secondary">
                        {photo.colorized_versions === 0
                          ? "grayscale"
                          : `${photo.colorized_versions} version${photo.colorized_versions > 1 ? "s" : ""}`}
                      </Badge>
                    </span>
                  </div>
                </Card>
              );
            })}
          </div>
          <div className="flex justify-end gap-2">
            <Button
              size="sm"
              variant="outline"
              disabled={cursors.length === 1}
              onClick={() => setCursors((c) => c.slice(0, -1))}
            >
              Previous
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={!data.next_cursor}
              onClick={() => setCursors((c) => [...c, data.next_cursor ?? undefined])}
            >
              Next
            </Button>
          </div>
        </>
      )}
      <PhotoDetailSheet photoKey={openKey} onOpenChange={(open) => !open && setOpenKey(undefined)} />
    </div>
  );
}
