"use client";

import { Line, OrbitControls, RoundedBox } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import { type Group, MathUtils, type Mesh, Vector3 } from "three";
import type { WorkflowDetail } from "@/types/api";
import { FitCamera, Floor, Scene3D, SceneLabel, useMediaQuery, useNarrowFrame, useReducedMotion } from "./Scene3D";

type Position = [number, number, number];

type StationState = "pending" | "running" | "done" | "failed" | "skipped" | "waiting" | "blocked";

interface Station {
  key: string;
  label: string;
  state: StationState;
}

const COLORS: Record<StationState, string> = {
  pending: "#3a4a5a",
  running: "#5aa0f2",
  done: "#3fbf8a",
  failed: "#ef5b5b",
  skipped: "#22303c",
  waiting: "#f5b35c",
  blocked: "#ef5b5b",
};

const STATE_TEXT: Record<StationState, string> = {
  pending: "Not started",
  running: "Running",
  done: "Done",
  failed: "Failed",
  skipped: "Not needed",
  waiting: "Waiting",
  blocked: "Stopped here",
};

const STAGES: { key: string; label: string; action?: string }[] = [
  { key: "plan", label: "Plan" },
  { key: "resolve_customer", label: "CRM lookup" },
  { key: "create_invoice", label: "Invoice", action: "invoice" },
  { key: "generate_report", label: "Report", action: "report" },
  { key: "draft_email", label: "Email draft", action: "email" },
  { key: "request_approval", label: "Approval gate" },
  { key: "execute_actions", label: "Execute" },
  { key: "complete", label: "Complete" },
];

const GATE_INDEX = 5;

/** One gentle arc on wide frames; two rows on phones, so labels keep their width. */
function stationPosition(index: number, narrow: boolean): Position {
  if (narrow) {
    const row = index < 4 ? 0 : 1;
    return [((index % 4) - 1.5) * 2.2, 0, row === 0 ? -1.5 : 1.7];
  }
  const x = (index - (STAGES.length - 1) / 2) * 1.85;
  return [x, 0, 0.8 - 0.03 * x * x];
}

export function buildStations(workflow: WorkflowDetail): Station[] {
  const steps = new Map(workflow.steps.map((s) => [s.step_key, s]));
  const actions = workflow.plan?.actions ?? [];
  const planned = workflow.plan !== null;
  const needsApproval = workflow.approvals.length > 0;
  const finished = ["succeeded", "failed", "rejected", "cancelled"].includes(workflow.status);
  const decision = workflow.approvals.at(-1)?.status;

  return STAGES.map((stage) => {
    const step = steps.get(stage.key);
    let state: StationState = "pending";
    if (step?.status === "succeeded") state = "done";
    else if (step?.status === "failed") state = "failed";
    else if (step?.status === "running") state = "running";
    else if (planned && stage.action && !actions.includes(stage.action)) state = "skipped";
    else if (planned && stage.key === "resolve_customer" && !actions.some((a) => a !== "report")) state = "skipped";
    else if (finished) state = "skipped";

    if (stage.key === "request_approval") {
      if (workflow.status === "waiting_for_approval" || decision === "pending") state = "waiting";
      else if (decision === "approved") state = "done";
      else if (decision === "rejected" || decision === "changes_requested" || decision === "expired") state = "blocked";
      else if (planned && !needsApproval && finished) state = "skipped";
    }
    return { key: stage.key, label: stage.label, state };
  });
}

export function describeWorkflow(stations: Station[]): string {
  const current =
    stations.find((s) => s.state === "failed" || s.state === "blocked" || s.state === "waiting" || s.state === "running") ??
    [...stations].reverse().find((s) => s.state === "done");
  const done = stations.filter((s) => s.state === "done").length;
  const applicable = stations.filter((s) => s.state !== "skipped").length;
  if (!current) return "This workflow has not started yet.";
  return `${done} of ${applicable} steps done. Currently at ${current.label}: ${STATE_TEXT[current.state]}.`;
}

function StationMesh({ station, position, reduced }: { station: Station; position: Position; reduced: boolean }) {
  const ref = useRef<Group>(null);
  const targetHeight = station.state === "skipped" ? 0.18 : station.state === "pending" ? 0.32 : 0.7;
  const color = COLORS[station.state];

  useFrame((frame, delta) => {
    if (!ref.current) return;
    const scale = reduced ? targetHeight : MathUtils.damp(ref.current.scale.y, targetHeight, 4, delta);
    ref.current.scale.y = scale;
    ref.current.position.y = scale / 2;
    if (!reduced && station.state === "running") {
      ref.current.position.y += Math.sin(frame.clock.elapsedTime * 4) * 0.03;
    }
  });

  return (
    <group position={position}>
      <group ref={ref} scale={[1, targetHeight, 1]} position={[0, targetHeight / 2, 0]}>
        <RoundedBox args={[1, 1, 1]} radius={0.08} smoothness={2}>
          <meshStandardMaterial
            color={color}
            emissive={color}
            emissiveIntensity={station.state === "running" || station.state === "waiting" ? 0.55 : 0.12}
            roughness={0.45}
            metalness={0.15}
            transparent={station.state === "skipped"}
            opacity={station.state === "skipped" ? 0.5 : 1}
          />
        </RoundedBox>
      </group>
      <SceneLabel position={[0, 0, 0.95]} title={station.label} detail={STATE_TEXT[station.state]} />
    </group>
  );
}

/** The gate is the point of the scene: it physically bars the track until a person decides. */
function GateDoors({ station, position, reduced }: { station: Station; position: Position; reduced: boolean }) {
  const left = useRef<Mesh>(null);
  const right = useRef<Mesh>(null);
  const open = station.state === "done" || station.state === "skipped";
  const color = station.state === "blocked" ? COLORS.blocked : open ? COLORS.done : COLORS.waiting;

  useFrame((_, delta) => {
    const target = open ? 0.92 : 0.28;
    for (const [mesh, sign] of [
      [left.current, -1],
      [right.current, 1],
    ] as const) {
      if (!mesh) continue;
      mesh.position.z = reduced ? sign * target : MathUtils.damp(mesh.position.z, sign * target, 3, delta);
    }
  });

  const [x, , z] = position;
  return (
    <group position={[x + 0.92, 0, z]}>
      <mesh ref={left} position={[0, 0.55, -0.28]}>
        <boxGeometry args={[0.1, 1.1, 0.56]} />
        <meshStandardMaterial color={color} emissive={color} emissiveIntensity={0.5} />
      </mesh>
      <mesh ref={right} position={[0, 0.55, 0.28]}>
        <boxGeometry args={[0.1, 1.1, 0.56]} />
        <meshStandardMaterial color={color} emissive={color} emissiveIntensity={0.5} />
      </mesh>
    </group>
  );
}

/** A marker that travels the track and stops at the furthest step reached. */
function Packet({ stations, positions, reduced }: { stations: Station[]; positions: Position[]; reduced: boolean }) {
  const ref = useRef<Mesh>(null);
  const target = useMemo(() => {
    let last = 0;
    stations.forEach((s, index) => {
      if (s.state !== "skipped" && s.state !== "pending") last = index;
    });
    const position = positions[last]!;
    return new Vector3(position[0], 1.05, position[2]);
  }, [stations, positions]);

  useFrame((frame, delta) => {
    if (!ref.current) return;
    if (reduced) {
      ref.current.position.copy(target);
      return;
    }
    ref.current.position.x = MathUtils.damp(ref.current.position.x, target.x, 2, delta);
    ref.current.position.z = MathUtils.damp(ref.current.position.z, target.z, 2, delta);
    ref.current.position.y = target.y + Math.sin(frame.clock.elapsedTime * 2.5) * 0.06;
  });

  return (
    <mesh ref={ref} position={[target.x, target.y, target.z]}>
      <sphereGeometry args={[0.13, 20, 20]} />
      <meshStandardMaterial color="#ffffff" emissive="#cfe6ff" emissiveIntensity={1.2} />
    </mesh>
  );
}

function Track({ positions }: { positions: Position[] }) {
  const points = useMemo(() => positions.map((p) => new Vector3(p[0], 0.02, p[2])), [positions]);
  return <Line points={points} color="#5b7083" lineWidth={2} />;
}

function Contents({ stations, reduced }: { stations: Station[]; reduced: boolean }) {
  const narrow = useNarrowFrame();
  const finePointer = useMediaQuery("(pointer: fine)");
  const positions = useMemo(() => STAGES.map((_, index) => stationPosition(index, narrow)), [narrow]);
  return (
    <>
      <FitCamera width={narrow ? 10.4 : 16.4} depth={narrow ? 10.5 : 5.4} />
      <color attach="background" args={["#0d1620"]} />
      <ambientLight intensity={0.55} />
      <directionalLight position={[4, 8, 6]} intensity={1.3} />
      <Floor />
      <Track positions={positions} />
      {stations.map((station, index) => (
        <StationMesh key={station.key} station={station} position={positions[index]!} reduced={reduced} />
      ))}
      <GateDoors station={stations[GATE_INDEX]!} position={positions[GATE_INDEX]!} reduced={reduced} />
      <Packet stations={stations} positions={positions} reduced={reduced} />
      {finePointer && (
        <OrbitControls
          enableZoom={false}
          enablePan={false}
          minPolarAngle={0.7}
          maxPolarAngle={1.2}
          minAzimuthAngle={-0.5}
          maxAzimuthAngle={0.5}
          target={[0, 0.4, 0]}
        />
      )}
    </>
  );
}

export function WorkflowScene({ workflow }: { workflow: WorkflowDetail }) {
  const reduced = useReducedMotion();
  const stations = useMemo(() => buildStations(workflow), [workflow]);
  return (
    <Scene3D summary={describeWorkflow(stations)} camera={{ position: [0, 6, 9], fov: 38 }}>
      <Contents stations={stations} reduced={reduced} />
    </Scene3D>
  );
}
