"use client";

import { useState } from "react";

import { cn } from "@/lib/utils";

interface BeforeAfterSliderProps {
  beforeUrl: string;
  afterUrl: string;
  alt: string;
  className?: string;
}

/**
 * Original underneath, colorized on top, revealed up to the slider position.
 * Both images are presigned B2 URLs rendered with plain <img>: they expire, so
 * routing them through next/image's optimizer cache would serve dead URLs.
 */
export function BeforeAfterSlider({ beforeUrl, afterUrl, alt, className }: BeforeAfterSliderProps) {
  const [position, setPosition] = useState(50);

  return (
    <div className={cn("relative w-full overflow-hidden rounded-md bg-muted select-none", className)}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={beforeUrl} alt={`${alt} (original)`} className="block h-auto w-full" />
      <div
        className="absolute inset-0"
        style={{ clipPath: `inset(0 ${100 - position}% 0 0)` }}
        aria-hidden
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={afterUrl} alt="" className="block h-auto w-full" />
      </div>
      <div
        aria-hidden
        className="pointer-events-none absolute inset-y-0 w-0.5 bg-white/90 shadow"
        style={{ left: `${position}%` }}
      />
      <span className="absolute left-2 top-2 rounded bg-black/60 px-1.5 py-0.5 text-[11px] font-medium text-white">
        Colorized
      </span>
      <span className="absolute right-2 top-2 rounded bg-black/60 px-1.5 py-0.5 text-[11px] font-medium text-white">
        Original
      </span>
      <input
        type="range"
        min={0}
        max={100}
        value={position}
        onChange={(e) => setPosition(Number(e.target.value))}
        aria-label="Reveal colorized version"
        className="absolute inset-0 h-full w-full cursor-ew-resize opacity-0"
      />
    </div>
  );
}
