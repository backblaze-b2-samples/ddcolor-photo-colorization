"use client";

import Link from "next/link";
import type { Batch } from "@ddcolor-photo-colorization/shared";
import { Layers } from "lucide-react";

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { EmptyState } from "@/components/ui/empty-state";
import { StatusBadge } from "@/components/common/status-badge";
import { modelLabel } from "@/lib/batch-labels";
import { formatDate, humanizeBytes } from "@/lib/utils";

const HEAD = "text-xs font-semibold uppercase tracking-wider text-muted-foreground";

export function BatchesTable({ batches, compact = false }: { batches: Batch[]; compact?: boolean }) {
  if (batches.length === 0) {
    return (
      <EmptyState
        icon={Layers}
        title="No batches yet"
        description="Create a batch to colorize your ingested photos."
      />
    );
  }
  return (
    <Table>
      <TableHeader>
        <TableRow className="bg-muted/40 hover:bg-muted/40">
          <TableHead className={HEAD}>Batch</TableHead>
          <TableHead className={HEAD}>Status</TableHead>
          <TableHead className={HEAD}>Photos</TableHead>
          {!compact && <TableHead className={HEAD}>Model</TableHead>}
          <TableHead className={HEAD}>Derived</TableHead>
          {!compact && <TableHead className={HEAD}>Created</TableHead>}
        </TableRow>
      </TableHeader>
      <TableBody>
        {batches.map((b) => (
          <TableRow key={b.batch_id} className="table-row-hover">
            <TableCell className="max-w-[16rem] font-medium">
              <Link
                href={`/batches/${b.batch_id}`}
                className="block truncate underline-offset-4 hover:underline"
              >
                {b.name}
              </Link>
            </TableCell>
            <TableCell>
              <StatusBadge status={b.status} />
            </TableCell>
            <TableCell className="tabular-nums text-muted-foreground">
              {b.done_count}/{b.photo_count}
              {b.failed_count > 0 && (
                <span className="ml-1 text-destructive">({b.failed_count} failed)</span>
              )}
            </TableCell>
            {!compact && (
              <TableCell className="whitespace-nowrap text-muted-foreground">
                {modelLabel(b.model_id)} @ {b.input_size}
              </TableCell>
            )}
            <TableCell className="whitespace-nowrap font-mono text-xs tabular-nums text-muted-foreground">
              {humanizeBytes(b.derived_bytes)}
            </TableCell>
            {!compact && (
              <TableCell className="whitespace-nowrap text-muted-foreground">
                {formatDate(b.created_at)}
              </TableCell>
            )}
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
