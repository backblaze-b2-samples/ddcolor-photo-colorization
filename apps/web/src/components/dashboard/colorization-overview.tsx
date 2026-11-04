"use client";

import Link from "next/link";
import { ArrowRight, Images, Layers, Palette, Repeat } from "lucide-react";
import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from "recharts";

import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { type ChartConfig, ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart";
import { ErrorState } from "@/components/ui/error-state";
import { Skeleton } from "@/components/ui/skeleton";
import { BatchesTable } from "@/components/batches/batches-table";
import { formatRatio } from "@/lib/batch-labels";
import { useBatchStats } from "@/lib/queries";
import { humanizeBytes } from "@/lib/utils";

const chartConfig = {
  bytes: { label: "Stored bytes", color: "var(--chart-1)" },
} satisfies ChartConfig;

export function ColorizationOverview() {
  const { data: stats, isLoading, error, refetch } = useBatchStats();

  if (error) {
    return (
      <Card>
        <CardContent className="p-0">
          <ErrorState error={error} onRetry={() => refetch()} />
        </CardContent>
      </Card>
    );
  }

  const cards = [
    { title: "Photos ingested", value: stats?.photos_ingested ?? 0, icon: Images },
    { title: "Photos colorized", value: stats?.photos_colorized ?? 0, icon: Palette },
    { title: "Batches run", value: stats?.batches_total ?? 0, icon: Layers },
  ];
  const chartData = [
    { label: "Grayscale originals", bytes: stats?.grayscale_bytes ?? 0 },
    { label: "Derived outputs", bytes: stats?.derived_bytes ?? 0 },
  ];

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card className="card-hover animate-fade-in-up stagger-1 border-primary/40">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 px-4 pt-4 pb-2">
            <CardTitle className="text-xs font-semibold text-muted-foreground">
              Write amplification
            </CardTitle>
            <div className="stat-icon-wrap">
              <Repeat className="h-4 w-4" />
            </div>
          </CardHeader>
          <CardContent className="px-4 pb-5">
            {isLoading ? (
              <Skeleton className="h-8 w-24" />
            ) : (
              <>
                <div className="stat-value">{formatRatio(stats?.amplification_ratio ?? 0)}</div>
                <p className="mt-1 text-xs text-muted-foreground">stored bytes per ingested byte</p>
              </>
            )}
          </CardContent>
        </Card>
        {cards.map((card, i) => (
          <Card key={card.title} className={`card-hover animate-fade-in-up stagger-${i + 2}`}>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 px-4 pt-4 pb-2">
              <CardTitle className="text-xs font-semibold text-muted-foreground">
                {card.title}
              </CardTitle>
              <div className="stat-icon-wrap">
                <card.icon className="h-4 w-4" />
              </div>
            </CardHeader>
            <CardContent className="px-4 pb-5">
              {isLoading ? <Skeleton className="h-8 w-24" /> : <div className="stat-value">{card.value}</div>}
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card className="animate-fade-in-up stagger-3">
          <CardHeader className="border-b border-border px-5 py-4">
            <CardTitle className="card-title">Bytes in B2</CardTitle>
            <CardDescription className="text-xs">
              Originals are never modified; every run adds colorized outputs, comparisons and a
              manifest next to them.
            </CardDescription>
          </CardHeader>
          <CardContent className="p-5">
            {isLoading ? (
              <Skeleton className="h-[220px] w-full" />
            ) : (
              <ChartContainer config={chartConfig} className="h-[220px] w-full">
                <BarChart data={chartData} margin={{ top: 8, right: 4, left: 8, bottom: 0 }}>
                  <CartesianGrid vertical={false} strokeDasharray="3 3" stroke="var(--border)" />
                  <XAxis dataKey="label" tickLine={false} axisLine={false} tickMargin={10} fontSize={11} />
                  <YAxis
                    tickLine={false}
                    axisLine={false}
                    fontSize={11}
                    width={64}
                    tickFormatter={(v: number) => humanizeBytes(v)}
                  />
                  <ChartTooltip
                    cursor={{ fill: "var(--accent-subtle)" }}
                    content={<ChartTooltipContent formatter={(v) => humanizeBytes(Number(v))} />}
                  />
                  <Bar dataKey="bytes" fill="var(--color-bytes)" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ChartContainer>
            )}
          </CardContent>
        </Card>

        <Card className="animate-fade-in-up stagger-4">
          <CardHeader className="border-b border-border px-5 py-4">
            <CardTitle className="card-title">Recent batches</CardTitle>
            <CardAction className="self-center">
              <Link
                href="/batches"
                className="inline-flex items-center gap-1 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground"
              >
                View all
                <ArrowRight className="h-3 w-3" />
              </Link>
            </CardAction>
          </CardHeader>
          <CardContent className="p-0">
            {isLoading ? (
              <div className="space-y-3 p-4">
                {Array.from({ length: 4 }).map((_, i) => (
                  <Skeleton key={i} className="h-10 w-full" />
                ))}
              </div>
            ) : (
              <BatchesTable batches={stats?.recent_batches ?? []} compact />
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
