"use client";

import { useState, type ImgHTMLAttributes } from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

/**
 * An `<img>` that shows a pulsing skeleton until it has painted, instead of a
 * blank gray box. Presigned B2 URLs can take a moment on a cold cache, and the
 * library and batch grids load many full-size images at once.
 *
 * Fills its parent, so the parent sets the box (e.g. `aspect-[4/3]`).
 */
export function LoadingImage({
  className,
  onLoad,
  onError,
  ...props
}: ImgHTMLAttributes<HTMLImageElement>) {
  // Keyed on src: a new URL shows the skeleton again until it loads.
  const [loadedSrc, setLoadedSrc] = useState<string | undefined>();
  const loaded = typeof props.src === "string" && loadedSrc === props.src;
  return (
    <>
      {!loaded && (
        <Skeleton aria-hidden className="absolute inset-0 rounded-none" data-testid="image-skeleton" />
      )}
      {/* eslint-disable-next-line @next/next/no-img-element, jsx-a11y/alt-text */}
      <img
        {...props}
        decoding="async"
        // An image served from cache can finish before React attaches onLoad.
        ref={(el) => {
          if (el?.complete && el.naturalWidth > 0 && loadedSrc !== el.getAttribute("src")) {
            setLoadedSrc(el.getAttribute("src") ?? undefined);
          }
        }}
        className={cn(className, "transition-opacity", loaded ? "opacity-100" : "opacity-0")}
        onLoad={(e) => {
          setLoadedSrc(e.currentTarget.getAttribute("src") ?? undefined);
          onLoad?.(e);
        }}
        onError={(e) => {
          // Stop pulsing on a broken image; the browser's broken-image state shows.
          setLoadedSrc(e.currentTarget.getAttribute("src") ?? undefined);
          onError?.(e);
        }}
      />
    </>
  );
}
