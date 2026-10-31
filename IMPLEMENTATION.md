# Enterprise AI Workflow Automation Platform

## Implementation Plan

**Project type:** Advanced Forward Deployed Engineering / AI Engineering
portfolio project\
**Goal:** Build a secure, observable, human-approved business automation
platform that accepts natural-language requests and executes workflows
across CRM, invoicing, reporting, and email systems.

------------------------------------------------------------------------

## 1. Product Vision

Businesses repeatedly perform tasks such as creating invoices, updating
CRM records, preparing reports, and emailing customers. This platform
turns those requests into traceable workflows.

A user submits a request such as:

> Create an invoice for customer Acme Ltd for the approved services,
> update the CRM account, generate a monthly summary, and prepare an
> email for the customer.

The system should: 1. Authenticate the user and check permissions. 2.
Parse the request into a structured workflow plan. 3. Retrieve required
customer and business data through integration tools. 4. Validate inputs
and business rules. 5. Generate invoice/report artifacts. 6. Pause for
human approval before sensitive actions. 7. Execute approved external
actions safely. 8. Recover from transient failures without duplicate
side effects. 9. Record every meaningful step in an audit trail. 10.
Display workflow status, approvals, artifacts, and errors in a
dashboard.

### Non-goals for the first release

-   Autonomous payment collection or money movement.
-   Sending external emails without approval.
-   Replacing a full accounting or CRM platform.
-   Training a foundation model.
-   Supporting every third-party CRM/accounting provider from day one.

------------------------------------------------------------------------

## 2. Recommended Technology Stack

  -----------------------------------------------------------------------
  Layer                   Technology              Responsibility
  ----------------------- ----------------------- -----------------------
  Web application         Next.js, TypeScript     Dashboard and user
                                                  experience

  UI                      Tailwind CSS, shadcn/ui Components and styling

  API                     Python, FastAPI,        REST API and validation
                          Pydantic                

  Agent orchestration     LangGraph               Stateful, resumable
                                                  workflows

  Local model             Ollama with a supported Local inference for
                          Qwen model              development

  Production model        Configurable hosted     Production inference
  adapter                 model provider          option

  Primary database        PostgreSQL              Users, workflows,
                                                  business data, audit

  Vector search           pgvector (optional)     Search over business
                                                  documents

  ORM and migrations      SQLAlchemy 2.x, Alembic Persistence and schema
                                                  evolution

  Queue/cache             Redis                   Broker/cache where
                                                  appropriate

  Background jobs         Celery                  Long-running and
                                                  scheduled work

  File storage            MinIO locally, S3 in    PDFs and report
                          production              artifacts

  Integrations            REST clients and MCP    CRM, email, accounting
                          adapters                systems

  Authentication          OAuth 2.0 / OpenID      Identity and
                          Connect, JWT session    authorization
                          strategy                

  PDF generation          ReportLab               Invoice and report PDFs

  Observability           OpenTelemetry,          Traces, metrics,
                          Prometheus, Grafana     dashboards

  Logging                 Python standard logging Structured application
                          / structlog             logs

  Backend tests           Pytest                  Unit and integration
                                                  tests

  Frontend tests          Playwright              Browser-level tests

  Containers              Docker, Docker Compose  Local and deployment
                                                  environments

  CI                      GitHub Actions          Lint, test, build

  Cloud target            AWS ECS, RDS, S3,       Production deployment
                          Secrets Manager         
  -----------------------------------------------------------------------

**Architecture rule:** LangGraph orchestrates business workflows. MCP
standardizes tool connectivity. They are complementary, not competing
agent frameworks. Do not add CrewAI or AutoGen to the initial
implementation.

------------------------------------------------------------------------

## 3. High-Level Architecture

``` mermaid
flowchart TD
    U[Business User] --> UI[Next.js Dashboard]
    UI --> API[FastAPI API]
    API --> AUTH[Authentication and RBAC]
    API --> WF[Workflow Service]
    WF --> LG[LangGraph Orchestrator]
    LG --> SUP[Supervisor / Planner]
    SUP --> CRM[CRM Tool / Agent]
    SUP --> INV[Invoice Service]
    SUP --> REP[Reporting Service]
    SUP --> VAL[Validation and Policy]
    VAL --> HITL[Human Approval Gate]
    HITL --> EMAIL[Email Tool / Agent]
    CRM --> EXT[External REST APIs / MCP Servers]
    EMAIL --> EXT
    INV --> DB[(PostgreSQL)]
    REP --> DB
    WF --> DB
    LG --> DB
    API --> REDIS[(Redis)]
    REDIS --> WORKER[Celery Workers]
    INV --> STORE[(MinIO / S3)]
    REP --> STORE
    API --> OBS[OpenTelemetry]
    WORKER --> OBS
    LG --> OBS
    OBS --> G[Grafana / Prometheus]
```

### Architectural boundaries

-   **Frontend:** presentation only; never holds provider secrets.
-   **FastAPI:** authentication, request validation, API contracts, and
    workflow lifecycle.
-   **Workflow layer:** creates and resumes LangGraph runs.
-   **Agent layer:** reasoning and tool selection; not a place for
    direct unrestricted database writes.
-   **Domain services:** deterministic invoice, CRM, reporting, and
    email operations.
-   **Integration adapters:** provider-specific API clients behind
    stable internal interfaces.
-   **Persistence:** durable workflow state, business records,
    approvals, idempotency records, and audit events.
-   **Workers:** execute long-running or scheduled tasks.
-   **Observability:** correlate API requests, workflow runs, tool
    calls, and external requests.

------------------------------------------------------------------------

## 4. Agent and Service Responsibilities

Use a supervisor-led LangGraph graph. Prefer a small number of focused
nodes and deterministic services over many autonomous agents.

  -----------------------------------------------------------------------
  Node / Service          Responsibility          Can perform external
                                                  side effects?
  ----------------------- ----------------------- -----------------------
  Supervisor              Interpret request and   No
                          route work              

  Planner                 Produce typed workflow  No
                          plan                    

  CRM integration         Read/create/update CRM  Only through authorized
                          records                 adapter

  Invoice service         Validate and generate   Creates internal
                          invoice/PDF             artifact

  Reporting service       Query approved data and Creates internal
                          create report           artifact

  Policy/validation       Check permissions,      No
                          totals, required        
                          fields, policy          

  Approval node           Pause and await         No
                          authorized human        
                          decision                

  Email integration       Send approved email     Yes, only after
                                                  approval

  Audit service           Append immutable-style  Writes audit records
                          audit events            
  -----------------------------------------------------------------------

Do not let an LLM invent customer IDs, invoice totals, recipient
addresses, or approval decisions. Resolve those values from trusted
records and validate them in deterministic code.

### Example workflow

``` mermaid
sequenceDiagram
    actor User
    participant UI as Dashboard
    participant API as FastAPI
    participant Graph as LangGraph
    participant CRM as CRM Adapter
    participant Invoice as Invoice Service
    participant Approval as Approval Service
    participant Mail as Email Adapter
    participant DB as PostgreSQL

    User->>UI: Submit business request
    UI->>API: POST /workflows
    API->>DB: Persist workflow and actor
    API->>Graph: Start workflow
    Graph->>CRM: Retrieve customer
    CRM-->>Graph: Verified customer data
    Graph->>Invoice: Create draft invoice
    Invoice->>DB: Persist draft and artifact metadata
    Graph->>DB: Record approval request
    Graph-->>UI: Awaiting approval
    User->>UI: Approve or reject
    UI->>API: POST /approvals/{id}/decision
    API->>DB: Verify approver and decision
    API->>Graph: Resume workflow
    alt Approved
        Graph->>Mail: Send approved email
        Mail-->>Graph: Provider result
        Graph->>DB: Record outcome and audit event
    else Rejected
        Graph->>DB: Record rejection
    end
    Graph-->>UI: Final workflow status
```

------------------------------------------------------------------------

## 5. Core Functional Requirements

### FR-01: User and organization management

-   Users can sign in through the configured identity provider.
-   Every business record belongs to an organization/tenant.
-   Roles: `admin`, `manager`, `operator`, `viewer`.
-   Enforce tenant and role checks on the backend for every protected
    operation.

### FR-02: Natural-language task intake

-   Accept a user request and optional supporting files.
-   Store the original request and normalized plan.
-   Return a workflow ID immediately.
-   Show the user the interpreted actions before execution when
    ambiguity or risk exists.

### FR-03: CRM integration

-   Search customers by stable identifiers and approved search fields.
-   Retrieve customer records.
-   Create or update records only when permitted.
-   Store provider record IDs and synchronization status.
-   Use a mock CRM adapter for local development.

### FR-04: Invoice generation

-   Generate a draft invoice from trusted customer and line-item data.
-   Validate currency, quantities, prices, tax rules, due date, and
    totals.
-   Use deterministic decimal arithmetic; never use floating point for
    money.
-   Assign unique invoice numbers safely.
-   Generate a PDF and store it in object storage.
-   Do not issue or email an invoice until the required approval is
    recorded.

### FR-05: Reporting

-   Generate reports from authorized, parameterized database queries.
-   Include reporting period, filters, generation time, and data
    provenance.
-   Store the report artifact and metadata.
-   Do not allow an LLM to generate arbitrary SQL and execute it
    directly.

### FR-06: Email

-   Prepare a draft with verified recipient, subject, body, and
    attachments.
-   Require explicit approval before sending.
-   Verify recipient against trusted CRM data or an authorized override
    flow.
-   Persist provider message ID and delivery status when available.
-   Never automatically retry an ambiguous send result without checking
    provider status or using a provider-supported idempotency mechanism.

### FR-07: Human approval

-   Approval request includes action summary, target, recipient, amount,
    artifacts, and risk level.
-   Only authorized roles may approve.
-   Support approve, reject, and request-changes decisions.
-   Approval is bound to a specific action payload/version. Any material
    change invalidates the previous approval.
-   Record approver identity, timestamp, decision, and reason.
-   Use LangGraph interrupt/resume or an equivalent durable pause
    mechanism.

### FR-08: Reliability and recovery

-   Apply bounded retries with exponential backoff and jitter to
    transient failures.
-   Do not retry validation, authorization, or other permanent failures.
-   Use idempotency keys for internal commands and provider-supported
    idempotency where available.
-   Use an outbox pattern for reliable event dispatch.
-   Track attempts, error category, next retry time, and final state.
-   Provide manual retry only to authorized users.

### FR-09: Audit and monitoring

-   Record actor, tenant, workflow, action, target, timestamp, result,
    correlation ID, and relevant metadata.
-   Do not log secrets, access tokens, full payment data, or unnecessary
    personal data.
-   Expose workflow metrics, tool latency, failure rate, retry count,
    and approval wait time.
-   Provide trace IDs in the dashboard and logs.

------------------------------------------------------------------------

## 6. Non-Functional Requirements

  -----------------------------------------------------------------------
  Area                                Requirement
  ----------------------------------- -----------------------------------
  Security                            Least privilege, encrypted
                                      transport, secret management,
                                      secure OAuth

  Authorization                       Tenant isolation and server-side
                                      RBAC

  Reliability                         Durable workflow state and bounded
                                      retries

  Idempotency                         Duplicate submissions must not
                                      create duplicate side effects

  Auditability                        Sensitive actions have actor,
                                      decision, and outcome records

  Performance                         API should acknowledge long
                                      workflows quickly and process
                                      asynchronously

  Maintainability                     Provider adapters and domain
                                      services are independently testable

  Observability                       Logs, metrics, traces share
                                      workflow and correlation IDs

  Privacy                             Minimize stored content and define
                                      retention policies

  Accessibility                       Dashboard supports keyboard
                                      navigation and clear status labels
  -----------------------------------------------------------------------

Set measurable service-level objectives after measuring a baseline; do
not invent production guarantees before load testing.

------------------------------------------------------------------------

## 7. Suggested Repository Structure

``` text
enterprise-ai-workflow/
├── frontend/
│   ├── app/
│   │   ├── (auth)/
│   │   ├── dashboard/
│   │   ├── workflows/
│   │   ├── approvals/
│   │   ├── integrations/
│   │   └── settings/
│   ├── components/
│   ├── lib/
│   ├── hooks/
│   ├── types/
│   ├── tests/
│   ├── package.json
│   └── Dockerfile
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   └── v1/
│   │   ├── core/
│   │   ├── auth/
│   │   ├── db/
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── repositories/
│   │   ├── services/
│   │   │   ├── workflows/
│   │   │   ├── invoices/
│   │   │   ├── reports/
│   │   │   ├── approvals/
│   │   │   └── audit/
│   │   ├── agents/
│   │   │   ├── graph.py
│   │   │   ├── state.py
│   │   │   ├── nodes/
│   │   │   ├── prompts/
│   │   │   └── tools/
│   │   ├── integrations/
│   │   │   ├── crm/
│   │   │   ├── email/
│   │   │   └── storage/
│   │   ├── workers/
│   │   ├── observability/
│   │   └── main.py
│   ├── migrations/
│   ├── tests/
│   │   ├── unit/
│   │   ├── integration/
│   │   └── contract/
│   ├── pyproject.toml
│   └── Dockerfile
├── infra/
│   ├── docker/
│   ├── monitoring/
│   └── aws/
├── docs/
│   ├── architecture/
│   ├── api/
│   └── decisions/
├── scripts/
├── .github/workflows/
├── docker-compose.yml
├── .env.example
├── IMPLEMENTATION.md
└── CLAUDE.md
```

Keep modules cohesive. Do not create empty folders or speculative
abstractions before they are needed.

------------------------------------------------------------------------

## 8. Data Model

Create migrations for at least these entities:

  -----------------------------------------------------------------------
  Entity                              Important fields
  ----------------------------------- -----------------------------------
  organizations                       id, name, created_at

  users                               id, organization_id,
                                      identity_subject, email, status

  memberships                         user_id, organization_id, role

  integrations                        id, organization_id, provider,
                                      status, secret_reference

  workflows                           id, organization_id, created_by,
                                      request_text, status,
                                      graph_thread_id, created_at

  workflow_steps                      id, workflow_id, step_key, status,
                                      input_summary, output_summary

  customers                           id, organization_id, provider,
                                      provider_customer_id, name, email

  invoices                            id, organization_id, customer_id,
                                      invoice_number, currency, subtotal,
                                      tax, total, status

  invoice_items                       id, invoice_id, description,
                                      quantity, unit_price, tax_rate,
                                      line_total

  artifacts                           id, organization_id, workflow_id,
                                      storage_key, media_type, checksum

  approval_requests                   id, workflow_id, action_type,
                                      payload_hash, status, requested_by,
                                      decided_by, decided_at

  idempotency_records                 organization_id, key, operation,
                                      status, result_reference

  audit_events                        id, organization_id, actor_id,
                                      workflow_id, action, target,
                                      result, correlation_id, created_at

  integration_operations              id, workflow_id, provider,
                                      operation, status, attempt_count,
                                      provider_request_id, last_error
  -----------------------------------------------------------------------

Use UUIDs, foreign keys, indexes, timestamps, and tenant-scoped
uniqueness constraints. Add soft deletion only where justified. Use
PostgreSQL `NUMERIC` for monetary amounts. Keep credentials in a secret
manager, not in the `integrations` table.

### Workflow states

`queued`, `running`, `waiting_for_approval`, `succeeded`, `failed`,
`rejected`, `cancelled`.

### Approval states

`pending`, `approved`, `rejected`, `changes_requested`, `expired`.

Use explicit state transitions enforced by application logic and, where
useful, database constraints.

------------------------------------------------------------------------

## 9. API Contract (Initial)

Prefix: `/api/v1`

  ----------------------------------------------------------------------------------------
  Method                  Endpoint                                Purpose
  ----------------------- --------------------------------------- ------------------------
  POST                    `/workflows`                            Submit a task

  GET                     `/workflows`                            List tenant workflows

  GET                     `/workflows/{workflow_id}`              Workflow detail and
                                                                  timeline

  POST                    `/workflows/{workflow_id}/cancel`       Cancel if safe

  POST                    `/workflows/{workflow_id}/retry`        Retry eligible failed
                                                                  workflow

  GET                     `/approvals`                            List pending approvals

  GET                     `/approvals/{approval_id}`              Approval detail

  POST                    `/approvals/{approval_id}/decision`     Approve/reject/request
                                                                  changes

  GET                     `/invoices`                             List invoices

  GET                     `/invoices/{invoice_id}`                Invoice detail

  GET                     `/artifacts/{artifact_id}`              Authorized artifact
                                                                  metadata/download

  GET                     `/integrations`                         List integration status

  POST                    `/integrations/{provider}/connect`      Start OAuth connection

  POST                    `/integrations/{provider}/disconnect`   Revoke integration

  GET                     `/health/live`                          Liveness

  GET                     `/health/ready`                         Readiness
  ----------------------------------------------------------------------------------------

### Example workflow request

``` json
{
  "request": "Create a draft invoice for Acme Ltd for the approved consulting services and prepare an email for approval.",
  "context": {
    "customer_reference": "acme-ltd",
    "currency": "INR"
  },
  "idempotency_key": "client-generated-unique-key"
}
```

### Example response

``` json
{
  "workflow_id": "uuid",
  "status": "queued",
  "created_at": "2026-01-01T10:00:00Z"
}
```

Use real generated values in the application. The examples above are
illustrative. Define request/response schemas in Pydantic and publish
OpenAPI documentation.

------------------------------------------------------------------------

## 10. Human Approval and Safety Design

Approval is a security boundary, not just a UI feature.

Sensitive actions include: - Sending an email to an external
recipient. - Issuing or finalizing an invoice. - Updating important CRM
fields. - Exporting reports containing confidential data. - Any action
that changes external business state.

Required controls: 1. Build an immutable approval snapshot containing
the exact action, target, recipient, amount, and artifact checksum. 2.
Hash the canonical action payload and store the hash with the approval.
3. On approval, re-check the actor's current permission and verify the
payload hash has not changed. 4. Expire or invalidate approvals when the
action changes or the approval window expires. 5. Execute the exact
approved payload, not a newly generated LLM interpretation. 6. Record
approval and execution outcomes in the audit log. 7. Do not treat model
output, email content, uploaded documents, or MCP tool responses as
trusted instructions.

For the demo, use mock integrations and a sandbox email provider.
Require a human approval before any external send.

------------------------------------------------------------------------

## 11. Failure Handling and Idempotency

### Error categories

-   `validation_error`: do not retry.
-   `authentication_error`: refresh credentials or request reconnection;
    do not loop.
-   `authorization_error`: do not retry.
-   `rate_limited`: retry according to provider guidance and
    `Retry-After`.
-   `transient_network_error`: bounded exponential backoff with jitter.
-   `provider_server_error`: bounded retry where operation semantics
    allow.
-   `unknown_outcome`: reconcile with provider before retrying side
    effects.

### Retry policy

-   Configure maximum attempts per operation.
-   Store attempt count and next retry timestamp.
-   Use exponential backoff with jitter and a maximum delay.
-   Respect provider rate limits.
-   Send exhausted operations to a failed/dead-letter state for human
    review.
-   Never retry a non-idempotent side effect blindly.

### Idempotency

-   Require a client idempotency key for workflow creation.
-   Derive stable operation keys for each workflow step.
-   Enforce uniqueness in PostgreSQL.
-   Use provider idempotency keys when supported.
-   For email providers without reliable idempotency, query/reconcile
    send status before retrying an uncertain request.
-   Use an outbox table for reliable publication of events after
    database commits.

------------------------------------------------------------------------

## 12. Security Requirements

-   Use OAuth 2.0 / OpenID Connect for provider and user authentication
    as appropriate.
-   Store secrets in AWS Secrets Manager in production; use local
    environment variables only for development.
-   Never commit `.env`, tokens, client secrets, or real customer data.
-   Enforce organization/tenant scoping in every repository query.
-   Apply RBAC on the backend, not only in the frontend.
-   Validate webhook signatures and OAuth state/PKCE.
-   Use HTTPS in deployed environments.
-   Apply rate limits and request-size limits.
-   Sanitize uploaded filenames and validate file type/size.
-   Use parameterized SQL; never execute raw LLM-generated SQL.
-   Protect against prompt injection from emails, CRM notes, and
    uploaded files.
-   Give each integration the minimum required scopes.
-   Redact sensitive values from logs and traces.
-   Add retention and deletion policies for customer data and artifacts.

------------------------------------------------------------------------

## 13. Implementation Phases

Build incrementally. Each phase must pass its acceptance criteria before
moving on.

### Phase 0 --- Repository and engineering foundation

Tasks: - Create repository and documented setup instructions. - Add
backend and frontend skeletons. - Add Docker Compose for PostgreSQL,
Redis, MinIO, backend, and frontend. - Add `.env.example`, formatting,
linting, and GitHub Actions. - Add health endpoints.

Acceptance: - A new developer can start the stack using documented
commands. - Health and readiness checks work. - No secrets are
committed.

### Phase 1 --- Database and authentication

Tasks: - Configure SQLAlchemy and Alembic. - Create organizations,
users, memberships, and integration tables. - Implement authentication
integration or a clearly isolated development auth adapter. - Implement
tenant-aware RBAC dependencies. - Add audit event persistence.

Acceptance: - Users cannot access another tenant's records. - Role
checks are tested at API level. - Migrations can create and upgrade the
schema.

### Phase 2 --- Workflow API and dashboard shell

Tasks: - Implement workflow create/list/detail endpoints. - Add workflow
status model and timeline. - Build dashboard, workflow list, and
workflow detail pages. - Add pagination, filtering, loading, empty, and
error states.

Acceptance: - User can submit a task and see a persisted workflow. - API
validation errors are clear. - UI reflects backend status.

### Phase 3 --- LangGraph orchestration

Tasks: - Define typed graph state with minimal necessary data. -
Implement planner/supervisor and deterministic routing. - Add mock CRM,
invoice, report, and email tools. - Persist graph checkpoints using a
supported durable checkpointer. - Add workflow tracing and node-level
audit events.

Acceptance: - A request executes a multi-step mock workflow. - Workflow
can resume after interruption/restart using persisted state. - LLM
output is schema-validated before use.

### Phase 4 --- CRM integration

Tasks: - Define a provider-neutral CRM interface. - Implement mock CRM
first. - Add one real CRM adapter only after the mock contract tests
pass. - Add OAuth lifecycle and token refresh securely. - Map provider
errors to normalized internal errors.

Acceptance: - Search and retrieve customer records. - Update operations
require authorization and audit logging. - Provider failures are
surfaced with actionable status.

### Phase 5 --- Invoice and artifact generation

Tasks: - Implement deterministic invoice domain service. - Validate line
items, currency, tax, totals, and invoice numbering. - Generate PDF with
ReportLab. - Store PDF in MinIO/S3. - Add authorized artifact download.

Acceptance: - Invoice totals match tested calculations. - Duplicate
workflow requests do not create duplicate invoices. - PDF artifact is
associated with the correct tenant and workflow.

### Phase 6 --- Reports

Tasks: - Define approved report types and parameter schemas. - Implement
parameterized repository queries. - Generate CSV/PDF report artifacts. -
Include source period and generation metadata.

Acceptance: - Reports use authorized data only. - Invalid filters are
rejected. - No arbitrary LLM-generated SQL is executed.

### Phase 7 --- Human approval

Tasks: - Implement approval request and decision endpoints. - Build
approval inbox and detail screen. - Bind approval to a canonical action
payload hash. - Implement graph interrupt and resume. - Enforce role,
tenant, expiry, and stale-payload checks.

Acceptance: - Workflow pauses before sensitive action. - Unauthorized
users cannot approve. - Changed payload invalidates approval. - Rejected
workflows never execute the protected action.

### Phase 8 --- Email integration

Tasks: - Implement email draft model and preview UI. - Add mock email
adapter and provider sandbox. - Validate recipients and attachments. -
Send only after approval. - Persist provider message IDs and reconcile
uncertain outcomes.

Acceptance: - Email cannot be sent without a valid approval. - Retry
does not create duplicate sends where provider support allows. - All
send attempts are auditable.

### Phase 9 --- Background jobs and resilience

Tasks: - Move long-running work to Celery workers where appropriate. -
Add Redis broker configuration and worker health checks. - Add bounded
retries, jitter, timeout handling, and dead-letter/manual-review
states. - Implement outbox dispatch and idempotency records. - Add
cancellation rules for safe-to-cancel operations.

Acceptance: - Temporary failures recover within configured retry
limits. - Permanent failures do not retry. - Ambiguous side effects are
reconciled before another attempt.

### Phase 10 --- Observability, security, and production hardening

Tasks: - Add OpenTelemetry traces across API, graph, workers, and
integrations. - Export metrics to Prometheus and build Grafana
dashboards. - Add structured logs and correlation IDs. - Perform
dependency, authorization, tenant-isolation, and prompt-injection
tests. - Add rate limits, secret management, backups, and retention
policy. - Load test and document measured limits.

Acceptance: - A workflow can be traced end-to-end. - Dashboard shows
throughput, failure rate, latency, retries, and approval wait time. -
Security tests pass. - Deployment and rollback procedures are
documented.

### Phase 11 --- AWS deployment and demonstration

Tasks: - Build production Docker images. - Deploy frontend/API/workers
to AWS ECS or an equivalent managed container platform. - Use RDS
PostgreSQL, S3, Secrets Manager, and managed Redis where appropriate. -
Configure TLS, DNS, logs, alarms, backups, and CI/CD. - Prepare seeded
demo tenant and mock/sandbox integrations.

Acceptance: - Staging deployment is reproducible. - No secrets are baked
into images. - Demo workflow can be executed, approved, completed, and
audited.

------------------------------------------------------------------------

## 14. Testing Strategy

### Unit tests

-   Invoice arithmetic and tax calculations.
-   Workflow state transitions.
-   Permission policies.
-   Payload canonicalization and hashing.
-   Retry classification and backoff.
-   Provider error normalization.

### Integration tests

-   PostgreSQL repositories and migrations.
-   Redis/Celery task execution.
-   LangGraph checkpoint and resume.
-   MinIO/S3 artifact storage.
-   Mock CRM and email adapters.

### Contract tests

-   Each provider adapter conforms to internal interfaces.
-   Validate request/response mapping and error mapping.
-   Use provider sandbox environments for real integration tests.

### End-to-end tests

1.  Submit a request.
2.  Retrieve customer from mock CRM.
3.  Generate invoice PDF.
4.  Pause for approval.
5.  Reject and verify no email is sent.
6.  Repeat and approve.
7.  Verify email provider mock receives exactly one send.
8.  Verify audit events and dashboard status.

### Security tests

-   Cross-tenant access attempts.
-   Role escalation attempts.
-   Approval by unauthorized users.
-   Replay of old approvals.
-   Prompt injection in CRM notes and uploaded documents.
-   Secret leakage in logs.
-   Malicious and oversized file uploads.

------------------------------------------------------------------------

## 15. Dashboard Pages

1.  **Overview:** workflow counts, success/failure trends, pending
    approvals, recent activity.
2.  **Workflows:** searchable list, status, creator, date, duration.
3.  **Workflow detail:** graph/timeline, step results, errors, retry
    history, trace ID.
4.  **Approvals:** pending actions, exact action summary,
    approve/reject/request changes.
5.  **Invoices:** invoice list, status, customer, amount, PDF preview.
6.  **Reports:** report history, filters, download.
7.  **Integrations:** provider connection status, scopes, last sync,
    reconnect.
8.  **Audit log:** actor, action, target, timestamp, result, correlation
    ID.
9.  **Settings:** organization, users, roles, retention, workflow
    policies.

------------------------------------------------------------------------

## 16. Demo Scenario

Use synthetic data only.

**Scenario:** A manager asks: "Prepare an invoice for Acme Ltd for 10
hours of approved consulting at ₹2,500 per hour, update the CRM note,
generate this month's sales summary, and prepare an email."

Expected demonstration: 1. Planner extracts requested actions. 2. CRM
adapter resolves Acme Ltd to a seeded customer record. 3. Invoice
service calculates ₹25,000 before tax and creates a draft. 4. Report
service creates a monthly summary from seeded sales data. 5. Email draft
includes verified recipient and PDF attachment. 6. Workflow pauses for
manager approval. 7. Dashboard displays exact actions and artifacts. 8.
Manager approves. 9. Mock email adapter records one send. 10. Audit page
shows every step and decision. 11. Demonstrate a simulated CRM timeout
and safe retry. 12. Demonstrate rejection and prove no email is sent.

------------------------------------------------------------------------

## 17. Definition of Done

A feature is complete only when: - It has typed request/response
schemas. - Business logic is separated from API and LLM code. -
Authorization and tenant checks are enforced. - Success and failure
paths are tested. - Side effects are idempotent or safely reconciled. -
Audit events are written. - Logs and traces contain correlation
identifiers. - User-facing loading, empty, and error states exist. -
Documentation and environment variables are updated. - No secrets or
real customer data are committed.

------------------------------------------------------------------------

## 18. Development Principles

-   Build mock integrations before connecting real providers.
-   Keep LLMs responsible for interpretation and planning, not
    arithmetic or authorization.
-   Use deterministic services for money, permissions, validation, and
    state transitions.
-   Require approval for external side effects.
-   Treat every external system as unreliable.
-   Prefer a modular monolith initially; split services only when
    scaling or ownership requires it.
-   Keep the first release small, testable, and demonstrable.

------------------------------------------------------------------------

## 19. Current Status

Last verified 2026-10-31. Setup and limitations are in `run.md`, and the
design as built is in `docs/architecture/overview.md`.

  -----------------------------------------------------------------------
  Phase                               Status
  ----------------------------------- -----------------------------------
  0 Foundation                        Built. Docker Compose and CI are
                                      written but have never run.

  1 to 8 Database, workflow API,      Built and tested against real
  LangGraph, CRM, invoices, reports,  PostgreSQL. CRM and email are mocks.
  approval, email

  9 Background jobs and resilience    Built. A real Celery worker and
                                      scheduler ran once by hand, with
                                      PostgreSQL as broker. Real Redis has
                                      not been used.

  10 Observability and hardening      Partly done. Metrics, logs, traces
                                      and security tests exist. The Grafana
                                      dashboard has not been opened. There
                                      is no load test, backup procedure or
                                      retention policy.

  11 AWS deployment                   Not started. It needs AWS accounts.
  -----------------------------------------------------------------------

### Differences from the plan above

-   A second local path runs without Docker; see
    `docs/decisions/0001-local-run-without-docker.md`.
-   `PLANNER_MODE` defaults to `rules`, and the model is opt-in; see
    `docs/decisions/0002-rules-planner-by-default.md`.
-   Sign-in is development-only until an identity provider is chosen.
    OIDC token checking is built and tested.
-   Added tables: `email_drafts`, `reports`, `sales_records`,
    `invoice_sequences`, `mock_crm_records`, `mock_emails`. Uploads are
    stored as artifacts.
