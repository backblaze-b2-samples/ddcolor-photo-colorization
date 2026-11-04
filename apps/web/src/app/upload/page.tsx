import Link from "next/link";

import { UploadForm } from "@/components/upload/upload-form";

export default function UploadPage() {
  return (
    <div className="space-y-8">
      <div className="animate-fade-in border-b border-border pb-5">
        <h1 className="page-title">Bulk Ingest</h1>
        <p className="mt-1.5 max-w-prose text-sm text-muted-foreground text-pretty">
          Drop black-and-white scans here: JPEG, PNG, TIFF, WebP or BMP, up to 100 MB each. They
          upload straight to <code>colorization/grayscale/</code> in B2 and are never modified.
          Colour photos are accepted too and flagged; the pipeline desaturates them before
          inference. Then colorize them from the{" "}
          <Link href="/photos" className="underline underline-offset-4">
            Photo Library
          </Link>{" "}
          or{" "}
          <Link href="/batches" className="underline underline-offset-4">
            Batches
          </Link>
          .
        </p>
      </div>
      <div className="animate-fade-in-up stagger-2">
        <UploadForm />
      </div>
    </div>
  );
}
