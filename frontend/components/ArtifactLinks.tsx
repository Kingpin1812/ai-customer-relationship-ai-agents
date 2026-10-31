"use client";

import { Download } from "lucide-react";
import { useState } from "react";
import { ApiError, downloadArtifact } from "@/lib/api";
import { Button } from "@/components/ui/button";

export function DownloadButton({
  artifactId,
  filename,
  label,
}: {
  artifactId: string;
  filename: string;
  label?: string;
}) {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  return (
    <span className="inline-flex flex-col items-start gap-1">
      <Button
        size="sm"
        variant="secondary"
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          setError(null);
          try {
            await downloadArtifact(artifactId, filename);
          } catch (e) {
            setError(e instanceof ApiError ? e.message : "Download failed.");
          } finally {
            setBusy(false);
          }
        }}
      >
        <Download aria-hidden />
        {label ?? filename}
      </Button>
      {error && (
        <span role="alert" className="text-xs text-danger">
          {error}
        </span>
      )}
    </span>
  );
}
