"use client";

import { Eye, EyeOff, Loader2 } from "lucide-react";
import { Component, type ReactNode, Suspense, useEffect, useState, useSyncExternalStore } from "react";
import { Html } from "@react-three/drei";
import { Canvas, useThree } from "@react-three/fiber";

const HIDE_KEY = "workflow.hide3d";

function webglAvailable(): boolean {
  try {
    const canvas = document.createElement("canvas");
    return Boolean(canvas.getContext("webgl2") ?? canvas.getContext("webgl"));
  } catch {
    return false;
  }
}

export function useMediaQuery(query: string): boolean {
  return useSyncExternalStore(
    (notify) => {
      const list = window.matchMedia(query);
      list.addEventListener("change", notify);
      return () => list.removeEventListener("change", notify);
    },
    () => window.matchMedia(query).matches,
    () => false,
  );
}

export function useReducedMotion(): boolean {
  return useMediaQuery("(prefers-reduced-motion: reduce)");
}

/** True on tall frames such as phones, where a scene should stack its layout. */
export function useNarrowFrame(): boolean {
  return useThree((state) => state.size.width / state.size.height < 1.5);
}

/** Pull the camera back just far enough that a scene of this size fills any frame shape. */
export function FitCamera({ width, depth }: { width: number; depth: number }) {
  const camera = useThree((state) => state.camera);
  const size = useThree((state) => state.size);
  const invalidate = useThree((state) => state.invalidate);

  useEffect(() => {
    if (!("fov" in camera)) return;
    const aspect = size.width / size.height;
    const halfFov = ((camera.fov as number) * Math.PI) / 360;
    const distance = Math.max(width / aspect, depth) / (2 * Math.tan(halfFov));
    camera.position.set(0, distance * 0.55, distance * 0.84);
    camera.lookAt(0, 0.4, 0);
    camera.updateProjectionMatrix();
    invalidate();
  }, [camera, size, width, depth, invalidate]);

  return null;
}

/**
 * A text label pinned to a point in the scene. It mounts one frame late: drei's Html can lose the
 * first label if it mounts in the same commit as the canvas.
 */
export function SceneLabel({
  position,
  title,
  detail,
}: {
  position: [number, number, number];
  title: string;
  detail: string;
}) {
  const [ready, setReady] = useState(false);
  useEffect(() => {
    const frame = requestAnimationFrame(() => setReady(true));
    return () => cancelAnimationFrame(frame);
  }, []);
  if (!ready) return null;
  return (
    <Html position={position} center zIndexRange={[5, 0]}>
      <div className="scene-label">
        <strong>{title}</strong>
        {detail}
      </div>
    </Html>
  );
}

/** A faint grid gives depth without a visible floor edge. */
export function Floor() {
  return <gridHelper args={[40, 40, "#22333f", "#17242f"]} position={[0, -0.01, 0]} />;
}

function Unavailable({ reason }: { reason: string }) {
  return (
    <div className="flex h-full items-center justify-center p-6 text-center text-sm text-stage-text/80">
      {reason} Everything shown here is also listed on this page.
    </div>
  );
}

/** A lost GL context or a scene crash must never take the page with it. */
class SceneBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    if (this.state.failed) return <Unavailable reason="The 3D view stopped working." />;
    return this.props.children;
  }
}

function SceneLoading() {
  return (
    <div role="status" className="absolute inset-0 flex items-center justify-center gap-2 text-sm text-stage-text/80">
      <Loader2 className="size-4 animate-spin" aria-hidden />
      Preparing 3D view…
    </div>
  );
}

/**
 * The frame every 3D view sits in. The canvas is decorative for assistive tech: `summary` gives the
 * same facts as text, and the page's DOM (timeline, tables) remains the source of truth.
 */
export function Scene3D({
  summary,
  camera,
  height = "h-72 sm:h-96",
  children,
}: {
  summary: string;
  camera: { position: [number, number, number]; fov: number };
  height?: string;
  children: ReactNode;
}) {
  const reduced = useReducedMotion();
  const [supported, setSupported] = useState<boolean | null>(null);
  const [hidden, setHidden] = useState(false);

  useEffect(() => {
    // Both values exist only in the browser, so they are read after hydration.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setSupported(webglAvailable());
    try {
      setHidden(localStorage.getItem(HIDE_KEY) === "1");
    } catch {
      // Storage blocked: show the scene.
    }
  }, []);

  const toggle = () => {
    const next = !hidden;
    setHidden(next);
    try {
      localStorage.setItem(HIDE_KEY, next ? "1" : "0");
    } catch {
      // Preference simply will not persist.
    }
  };

  return (
    <div className="relative overflow-hidden rounded-lg bg-stage text-stage-text" data-testid="scene-3d">
      <p className="sr-only">{summary}</p>
      <button
        type="button"
        onClick={toggle}
        aria-pressed={hidden}
        className="absolute top-2 right-2 z-10 inline-flex h-8 items-center gap-1.5 rounded-md bg-white/10 px-2.5 text-xs text-stage-text hover:bg-white/20"
      >
        {hidden ? <Eye className="size-3.5" aria-hidden /> : <EyeOff className="size-3.5" aria-hidden />}
        {hidden ? "Show 3D" : "Hide 3D"}
      </button>
      {hidden ? (
        <div className="px-4 py-3 pr-28 text-sm text-stage-text/80">{summary}</div>
      ) : (
        <div className={height} aria-hidden>
          {supported === false && <Unavailable reason="3D is not available on this device." />}
          {supported === null && <SceneLoading />}
          {supported && (
            <SceneBoundary>
              <Suspense fallback={<SceneLoading />}>
                <Canvas
                  dpr={[1, 1.5]}
                  camera={camera}
                  frameloop={reduced ? "demand" : "always"}
                  gl={{ antialias: true, powerPreference: "low-power" }}
                  fallback={<Unavailable reason="3D is not available on this device." />}
                >
                  {children}
                </Canvas>
              </Suspense>
            </SceneBoundary>
          )}
        </div>
      )}
    </div>
  );
}
