"use client";

import { Plus } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ErrorState } from "@/components/ui/error-state";
import { Skeleton } from "@/components/ui/skeleton";
import { BatchesTable } from "@/components/batches/batches-table";
import { CreateBatchDialog } from "@/components/batches/create-batch-dialog";
import { useBatches } from "@/lib/queries";

export default function BatchesPage() {
  const { data: batches, isLoading, error, refetch } = useBatches();

  return (
    <div className="space-y-8">
      <div className="animate-fade-in flex flex-wrap items-start justify-between gap-4 border-b border-border pb-5">
        <div>
          <h1 className="page-title">Batches</h1>
          <p className="mt-1.5 max-w-prose text-sm text-muted-foreground">
            Each batch colorizes a set of grayscale originals with one DDColor configuration and
            writes its outputs, comparisons and manifest CSV back to B2.
          </p>
        </div>
        <CreateBatchDialog
          trigger={
            <Button size="sm" className="h-8">
              <Plus aria-hidden className="h-3.5 w-3.5" />
              New batch
            </Button>
          }
        />
      </div>
      <Card className="animate-fade-in-up stagger-2">
        <CardContent className="p-0">
          {isLoading ? (
            <div className="space-y-3 p-4">
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className="h-10 w-full" />
              ))}
            </div>
          ) : error ? (
            <ErrorState error={error} onRetry={() => refetch()} />
          ) : (
            <BatchesTable batches={batches ?? []} />
          )}
        </CardContent>
      </Card>
    </div>
  );
}
