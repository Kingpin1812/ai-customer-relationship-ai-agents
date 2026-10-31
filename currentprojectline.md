# Current project line

Updated 2026-10-31. The MVP is finished and tested on this machine without Docker. Nothing is committed, because the folder is not a git repository.

Start here: `run.md`.

| Part | Status |
|---|---|
| Backend, database, workflow engine, approval gate | Done, tested |
| Frontend and 3D scenes | Done, tested |
| Docs: `run.md`, architecture, decisions, `IMPLEMENTATION.md` status | Done |
| Final review | Done, confirmed bugs fixed, 5 minor items deferred (below) |
| Docker Compose, Dockerfiles, CI, Grafana | **Written, never run** |
| AWS deployment (Phase 11) | Left out on purpose; it needs your accounts |

## Last test results (2026-10-31, on the final code)

| Check | Result |
|---|---|
| Backend tests (pytest) | 277 passed |
| Backend lint and format (ruff) | Clean |
| Backend types (mypy) | Clean, with `strict_optional = false` and `arg-type` off for API routes |
| Browser tests (Playwright) | 14 passed, run alone |
| Frontend type check, build | Clean |
| Frontend lint | 0 errors, 1 warning (`window.location.assign` in `frontend/lib/api.ts`) |
| npm audit | Production dependencies 0. 16 moderate in dev tooling (eslint, minimatch), left alone because the offered fix is a breaking `--force` |

Checked by hand, once: dev mode through the web proxy; the real `llama3.2` model end to end; a real Celery worker and scheduler with PostgreSQL as broker; the standalone frontend build the Docker image uses.

## Next steps, in order

1. Install Docker, then follow "Option 2" in `run.md`. Expect small fixes. Check that the MinIO image pulls, then open the Grafana dashboard.
2. `git init`, make a first commit, and push to GitHub so CI runs for the first time.
3. Fix the deferred minor items below.
4. Choose an identity provider and build the login screen.
5. Add a load test, backup procedure and retention policy (rest of Phase 10).
6. Phase 11, AWS, when accounts are available.

## Deferred minor items

- Report totals add across currencies. Nothing can create non-INR sales yet.
- Two admins demoting each other at the same moment can leave no admin (`backend/app/api/v1/members.py`).
- Unhandled 500 responses miss `X-Correlation-ID` and the request metric.
- Oversized bodies sent through the web proxy get a generic 400 instead of 413. They are still refused.
- The `invoice.issued` audit row repeats when a run is re-entered.

## Choices made for you

All of these can be changed.

- **Planner defaults to rules.** The model is opt-in with `PLANNER_MODE=auto`. `llama3.2` works here at about 20 to 40 seconds per request; `qwen3` is too slow. See `docs/decisions/0002-rules-planner-by-default.md`.
- **Tax 18%, payment terms 30 days:** placeholders, because the spec leaves tax rules open. Demo invoice: ₹25,000 + ₹4,500 = ₹29,500.
- **Self-approval is on:** the spec's demo has a manager both asking and approving. Turn it off with `ALLOW_SELF_APPROVAL=false`.
- **One approval covers the bundle:** issuing the invoice, the CRM note and the email are approved together.
- **"Request changes" ends the workflow as `rejected`,** with the reason shown. The user then submits again, because the spec allows only seven statuses.
- **"Prepare an email" sends it after approval,** as the spec's demo expects.
- **Customer emails use fixed templates.** No AI text or CRM notes reach the customer, and only the invoice PDF is attached, not the report.
- **Local run without Docker:** embedded PostgreSQL, background threads, files on disk.
- **Docker worker uses a thread pool,** so one process holds all its metrics.
- **MinIO image comes from Quay,** because its Docker Hub repository is gone. Override it with `MINIO_IMAGE`.
- **Added tables and fields:** `email_drafts`, `reports`, `sales_records`, `invoice_sequences`, mock CRM and email tables, `customer_id` on workflows. Uploads are stored as artifacts.
- **Rate limit is per API process,** not shared across instances.
- **`authentication_error` can be retried by hand** after an admin reconnects the provider.

## Things outside the app

- The `superpowers/` folder is only a reference copy and is listed in `.gitignore`. You can delete it.
- AVG Antivirus inspects HTTPS. New Python virtual environments need `pip install --use-feature=truststore --upgrade pip` once, which keeps certificate checks on.
- The Serena plugin's MCP server still fails to connect at session start. This has not been looked at.
- Progress ledger with every ruling: `.superpowers/sdd/2026-10-30-enterprise-ai-workflow-mvp/progress.md`.
