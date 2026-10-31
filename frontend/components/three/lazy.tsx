"use client";

import dynamic from "next/dynamic";
import { Loader2 } from "lucide-react";

function Placeholder() {
  return (
    <div role="status" className="flex h-72 items-center justify-center gap-2 rounded-lg bg-stage text-sm text-stage-text/80 sm:h-96">
      <Loader2 className="size-4 animate-spin" aria-hidden />
      Preparing 3D view…
    </div>
  );
}

// three.js is large and browser-only, so pages load it on demand and work without it.
export const LazyWorkflowScene = dynamic(
  () => import("./WorkflowScene").then((m) => m.WorkflowScene),
  { ssr: false, loading: Placeholder },
);

export const LazySystemScene = dynamic(() => import("./SystemScene").then((m) => m.SystemScene), {
  ssr: false,
  loading: Placeholder,
});
