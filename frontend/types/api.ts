export type WorkflowStatus =
  | "queued"
  | "running"
  | "waiting_for_approval"
  | "succeeded"
  | "failed"
  | "rejected"
  | "cancelled";

export type ApprovalStatus = "pending" | "approved" | "rejected" | "changes_requested" | "expired";

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface Me {
  user_id: string;
  email: string;
  display_name: string;
  organization_id: string;
  organization_name: string;
  role: "admin" | "manager" | "operator" | "viewer";
  permissions: string[];
  fault_injection_enabled: boolean;
  sandbox_enabled: boolean;
}

export interface WorkflowSummary {
  id: string;
  request_summary: string;
  creator_email: string;
  status: WorkflowStatus;
  created_at: string;
  duration_seconds: number | null;
  needs_clarification: boolean;
  error_category: string | null;
}

export interface Step {
  step_key: string;
  status: string;
  output_summary: string | null;
  error: string | null;
  runs: number;
  started_at: string;
  finished_at: string | null;
}

export interface Artifact {
  id: string;
  kind: string;
  filename: string;
  media_type: string;
  size_bytes: number;
  checksum: string;
  created_at: string;
}

export interface Operation {
  provider: string;
  operation: string;
  status: string;
  attempt_count: number;
  error_category: string | null;
  last_error: string | null;
  next_retry_at: string | null;
  provider_request_id: string | null;
  updated_at: string;
}

export interface ApprovalBrief {
  id: string;
  status: ApprovalStatus;
  summary: string;
  risk_level: string;
  decided_at: string | null;
  reason: string | null;
  invalidation_reason: string | null;
  created_at: string;
}

export interface Plan {
  actions: string[];
  customer_reference: string | null;
  line_items: { description: string; quantity: string; unit_price: string }[];
  currency: string | null;
  report: { type: string; period: string } | null;
  issue_invoice: boolean;
  clarifications: string[];
}

export interface EmailDraft {
  recipient: string;
  subject: string;
  body: string;
  status: string;
  provider_message_id: string | null;
  sent_at: string | null;
}

export interface WorkflowDetail {
  id: string;
  request_text: string;
  context: Record<string, string>;
  plan: Plan | null;
  planner_source: string | null;
  status: WorkflowStatus;
  creator_email: string;
  error_category: string | null;
  error_message: string | null;
  needs_clarification: boolean;
  can_retry: boolean;
  can_cancel: boolean;
  correlation_id: string | null;
  trace_id: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  steps: Step[];
  artifacts: Artifact[];
  approvals: ApprovalBrief[];
  operations: Operation[];
  timeline: { action: string; target: string; result: string; created_at: string }[];
  invoice_id: string | null;
  email_draft: EmailDraft | null;
}

export interface ArtifactRef {
  artifact_id: string;
  filename: string;
  checksum: string;
}

export type ApprovalAction =
  | {
      type: "issue_invoice";
      invoice_id: string;
      invoice_number: string;
      currency: string;
      subtotal: string;
      tax: string;
      total: string;
      due_date: string;
      artifact: ArtifactRef | null;
    }
  | { type: "update_crm_note"; provider: string; provider_customer_id: string; note: string }
  | {
      type: "send_email";
      provider: string;
      to: string;
      subject: string;
      body: string;
      attachments: ArtifactRef[];
    };

export interface Approval {
  id: string;
  workflow_id: string;
  action_type: string;
  summary: string;
  risk_level: string;
  status: ApprovalStatus;
  payload: {
    customer: { id: string; provider_customer_id: string; name: string };
    actions: ApprovalAction[];
  };
  payload_hash: string;
  amount: string | null;
  currency: string | null;
  recipient: string | null;
  requested_by_email: string;
  decided_by_email: string | null;
  decided_at: string | null;
  reason: string | null;
  invalidation_reason: string | null;
  expires_at: string;
  created_at: string;
}

export interface Invoice {
  id: string;
  workflow_id: string;
  invoice_number: string;
  customer_name: string;
  currency: string;
  subtotal: string;
  tax: string;
  total: string;
  status: string;
  issue_date: string;
  due_date: string;
  artifact_id: string | null;
}

export interface Report {
  id: string;
  workflow_id: string;
  report_type: string;
  period_start: string;
  period_end: string;
  filters: Record<string, string>;
  source: Record<string, string>;
  summary: {
    total: string;
    rows: { customer_name: string; currency: string; sales_count: number; amount: string }[];
  };
  generated_at: string;
  pdf_artifact_id: string | null;
  csv_artifact_id: string | null;
}

export interface Integration {
  id: string;
  provider: string;
  kind: string;
  status: string;
  scopes: string[];
  last_success_at: string | null;
}

export interface AuditEvent {
  id: string;
  created_at: string;
  actor_email: string | null;
  action: string;
  target: string;
  workflow_id: string | null;
  result: string;
  correlation_id: string | null;
  metadata: Record<string, unknown>;
}

export interface Member {
  user_id: string;
  email: string;
  display_name: string;
  role: Me["role"];
  status: string;
}

export interface SandboxEmail {
  provider_message_id: string;
  recipient: string;
  subject: string;
  body: string;
  attachments: { filename: string; checksum: string }[];
  sent_at: string;
}

export interface DashboardSummary {
  total: number;
  by_status: Record<WorkflowStatus, number>;
  pending_approvals: number;
  recent_activity: {
    action: string;
    target: string;
    result: string;
    workflow_id: string | null;
    actor_email: string | null;
    created_at: string;
  }[];
  integrations: {
    provider: string;
    kind: string;
    status: string;
    last_success_at: string | null;
  }[];
  trend: { day: string; succeeded: number; failed: number }[];
}
