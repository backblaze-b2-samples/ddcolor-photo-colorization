"use client";

import { cn } from "@/lib/utils";

interface SegmentedControlProps<T extends string | number> {
  value: T;
  onChange: (value: T) => void;
  options: { value: T; label: string }[];
  "aria-label": string;
  disabled?: boolean;
}

/**
 * A compact selector for a handful of mutually exclusive values (input size,
 * output format). Radio semantics, so keyboard and screen readers treat it as
 * one choice rather than a row of unrelated buttons.
 */
export function SegmentedControl<T extends string | number>({
  value,
  onChange,
  options,
  disabled,
  ...rest
}: SegmentedControlProps<T>) {
  return (
    <div
      role="radiogroup"
      aria-label={rest["aria-label"]}
      className="inline-flex rounded-md border border-border bg-muted/40 p-0.5"
    >
      {options.map((option) => {
        const selected = option.value === value;
        return (
          <button
            key={String(option.value)}
            type="button"
            role="radio"
            aria-checked={selected}
            disabled={disabled}
            onClick={() => onChange(option.value)}
            className={cn(
              "rounded-[5px] px-3 py-1 text-sm font-medium transition-colors disabled:opacity-50",
              selected
                ? "bg-background text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
