import Link from "next/link";
import { Layers, Upload } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ColorizationOverview } from "@/components/dashboard/colorization-overview";

export default function DashboardPage() {
  return (
    <div className="space-y-8">
      <div className="animate-fade-in flex flex-wrap items-start justify-between gap-4 border-b border-border pb-5">
        <div>
          <h1 className="page-title">Dashboard</h1>
          <p className="mt-1.5 text-sm text-muted-foreground">
            Colorization runs over your archive, and how much each run adds to Backblaze B2.
          </p>
        </div>
        <div className="flex gap-2">
          <Button asChild size="sm" variant="outline" className="h-8">
            <Link href="/upload">
              <Upload className="h-3.5 w-3.5" />
              Ingest photos
            </Link>
          </Button>
          <Button asChild size="sm" className="h-8">
            <Link href="/batches">
              <Layers className="h-3.5 w-3.5" />
              Batches
            </Link>
          </Button>
        </div>
      </div>
      <ColorizationOverview />
    </div>
  );
}
