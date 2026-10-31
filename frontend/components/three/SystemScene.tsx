"use client";

import { RoundedBox } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import { useRef } from "react";
import { type Group, MathUtils, type Mesh } from "three";
import { humanize } from "@/lib/utils";
import type { DashboardSummary, WorkflowStatus } from "@/types/api";
import { FitCamera, Floor, Scene3D, SceneLabel, useNarrowFrame, useReducedMotion } from "./Scene3D";

const PILLARS: { status: WorkflowStatus; color: string; label?: string }[] = [
  { status: "queued", color: "#7b8b9a" },
  { status: "running", color: "#5aa0f2" },
  { status: "waiting_for_approval", color: "#f5b35c", label: "Waiting" },
  { status: "succeeded", color: "#3fbf8a" },
  { status: "failed", color: "#ef5b5b" },
  { status: "rejected", color: "#d17bc0" },
  { status: "cancelled", color: "#4b5a68" },
];

function Pillar({
  position,
  count,
  max,
  color,
  label,
  reduced,
}: {
  position: [number, number, number];
  count: number;
  max: number;
  color: string;
  label: string;
  reduced: boolean;
}) {
  const ref = useRef<Group>(null);
  const height = 0.15 + (count / Math.max(max, 1)) * 2;

  useFrame((_, delta) => {
    if (!ref.current) return;
    const value = reduced ? height : MathUtils.damp(ref.current.scale.y, height, 3, delta);
    ref.current.scale.y = value;
    ref.current.position.y = value / 2;
  });

  return (
    <group position={position}>
      <group ref={ref} scale={[1, height, 1]} position={[0, height / 2, 0]}>
        <RoundedBox args={[0.8, 1, 0.8]} radius={0.06} smoothness={2}>
          <meshStandardMaterial color={color} emissive={color} emissiveIntensity={0.25} roughness={0.5} />
        </RoundedBox>
      </group>
      <SceneLabel position={[0, 0, 0.85]} title={String(count)} detail={label} />
    </group>
  );
}

/** Pending approvals sit at the centre: the part of the system that needs a person. */
function Core({ pending, position, reduced }: { pending: number; position: [number, number, number]; reduced: boolean }) {
  const ref = useRef<Mesh>(null);
  useFrame((frame, delta) => {
    if (!ref.current || reduced) return;
    ref.current.rotation.y += delta * 0.4;
    if (pending > 0) ref.current.scale.setScalar(1 + Math.sin(frame.clock.elapsedTime * 2.2) * 0.06);
  });
  const color = pending > 0 ? "#f5b35c" : "#3d5266";
  return (
    <group position={position}>
      <mesh ref={ref}>
        <icosahedronGeometry args={[0.5, 1]} />
        <meshStandardMaterial color={color} emissive={color} emissiveIntensity={0.5} flatShading />
      </mesh>
      <SceneLabel position={[0, -0.75, 0.85]} title={String(pending)} detail="Pending approvals" />
    </group>
  );
}

/** Seven status pillars, then pending approvals as the eighth place in the row. */
function rowPosition(index: number, narrow: boolean): [number, number, number] {
  if (narrow) {
    return [((index % 4) - 1.5) * 2.3, 0, index < 4 ? -1.7 : 1.6];
  }
  const x = (index - 3.5) * 1.85;
  return [x, 0, 0.6 - 0.03 * x * x];
}

function Contents({ summary, max, reduced }: { summary: DashboardSummary; max: number; reduced: boolean }) {
  const narrow = useNarrowFrame();
  return (
    <>
      <FitCamera width={narrow ? 10.4 : 16.4} depth={narrow ? 10.5 : 5.4} />
      <color attach="background" args={["#0d1620"]} />
      <ambientLight intensity={0.55} />
      <directionalLight position={[4, 8, 6]} intensity={1.3} />
      <Floor />
      {PILLARS.map((pillar, index) => (
        <Pillar
          key={pillar.status}
          position={rowPosition(index, narrow)}
          count={summary.by_status[pillar.status] ?? 0}
          max={max}
          color={pillar.color}
          label={pillar.label ?? humanize(pillar.status)}
          reduced={reduced}
        />
      ))}
      <Core pending={summary.pending_approvals} position={rowPosition(PILLARS.length, narrow).map((v, i) => (i === 1 ? 0.75 : v)) as [number, number, number]} reduced={reduced} />
    </>
  );
}

export function SystemScene({ summary }: { summary: DashboardSummary }) {
  const reduced = useReducedMotion();
  const max = Math.max(...PILLARS.map((p) => summary.by_status[p.status] ?? 0));
  const text =
    `${summary.total} workflows in total. ` +
    PILLARS.map((p) => `${humanize(p.status)}: ${summary.by_status[p.status] ?? 0}`).join(", ") +
    `. ${summary.pending_approvals} pending approvals.`;

  return (
    <Scene3D summary={text} camera={{ position: [0, 6, 9], fov: 38 }} height="h-72 sm:h-80">
      <Contents summary={summary} max={max} reduced={reduced} />
    </Scene3D>
  );
}
