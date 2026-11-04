"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft } from "lucide-react";

import { ErrorState } from "@/components/ui/error-state";
import { Skeleton } from "@/components/ui/skeleton";
import { BatchDetailView } from "@/components/batches/batch-detail-view";
import { useBatch } from "@/lib/queries";

export default function BatchPage() {
  const params = useParams<{ id: string }>();
  const batchId = params?.id ?? "";
  const { data: batch, isLoading, error, refetch } = useBatch(batchId);

  return (
    <div className="space-y-6">
      <Link
        href="/batches"
        className="inline-flex items-center gap-1 text-xs font-medium text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft aria-hidden className="h-3 w-3" />
        All batches
      </Link>
      {isLoading ? (
        <div className="space-y-4">
          <Skeleton className="h-10 w-1/2" />
          <Skeleton className="h-32 w-full" />
        </div>
      ) : error ? (
        <ErrorState error={error} onRetry={() => refetch()} />
      ) : batch ? (
        <BatchDetailView batch={batch} />
      ) : null}
    </div>
  );
}
