# Tripwire Implementation Plan

This implementation plan details the phases, milestones, quality gates, and deliverables for Tripwire.

---

### Phase 1 — Discovery & Baseline Configuration
- [x] Inspect workspace, environment, Python versions, and available packages.
- [x] Locate and extract PRD PDF (`PRD Tripwire - Decision Cascade for Safe AWS Agents.pdf`).
- [x] Document official Hackathon requirements in `docs/REQUIREMENTS.md`.
- [x] Create `docs/IMPLEMENTATION_PLAN.md`.
- [x] Create project skeleton (`agent/`, `tripwire_pattern/`, `dashboard/`, `eval/`, `tests/`, `examples/`, `docs/`, `scripts/`).
- [x] Create `.env.example`, `.gitignore`, `pyproject.toml`, `requirements.txt`, `LICENSE` (MIT).

### Phase 2 — Minimal Working Vertical Slice
- [ ] Build in-memory mock AWS environment in `agent/tools.py` (`list_instances`, `describe_instance`, `start_instance`, `stop_instance`, `delete_bucket`).
- [ ] Build Pydantic schemas in `tripwire_pattern/schemas.py`.
- [ ] Implement typed question in `tripwire_pattern/question.py` ("Are all arguments of this tool call supported by the user's request?").
- [ ] Build deterministic policy engine in `tripwire_pattern/policy.py`.
- [ ] Implement Strands tool-intervention handler in `tripwire_pattern/handler.py` and cascade in `tripwire_pattern/cascade.py`.
- [ ] Implement Decider client in `tripwire_pattern/decider_client.py` (with support for both live `strands-decider` server and deterministic local evaluation mode).
- [ ] Implement structured JSONL audit logger in `tripwire_pattern/audit.py` with secret redaction.
- [ ] Connect minimal Strands Agent in `agent/agent.py`.
- [ ] Verify vertical slice: allow grounded call, block hallucinated call, assert zero execution on block.

### Phase 3 — Security & Full Decision Cascade
- [ ] Implement all 4 lanes:
  - **ALLOW Lane**: Grounded arguments, confident Decider score (>= 0.85), deterministic policy passes, caller authorized.
  - **ASK Lane**: Ambiguous targets or missing parameters (0.60 <= score < 0.85), returns clarification request, pending action token with TTL & replay defense.
  - **ESCALATE Lane**: Low confidence (< 0.60) or unsure, routes to Bedrock LLM Judge in `tripwire_pattern/judge.py` with fail-closed fallback.
  - **BLOCK Lane**: Ungrounded, prompt injection, policy violation, destructive tool without explicit override.
- [ ] Implement role-based caller authorization in `tripwire_pattern/authorization.py`.
- [ ] Enforce fail-closed handling on all exceptions, timeouts, and network disconnects.

### Phase 4 — Automated Test Suite
- [ ] Unit tests (`tests/unit/`):
  - `test_cascade.py`: 4 lanes routing, threshold validation.
  - `test_policy.py`: Environment segregation (staging vs prod), destructive tools.
  - `test_tools.py`: In-memory state changes only on approval.
  - `test_audit.py`: Secret scrubbing, structured JSONL schema.
- [ ] Integration tests (`tests/integration/`):
  - `test_agent_intervention.py`: Strands agent tool intercept lifecycle.
  - `test_escalation.py`: LLM judge fallback and validation.
- [ ] Security tests (`tests/security/`):
  - `test_prompt_injection.py`: Adversarial text cannot trigger tool execution.
  - `test_environment_confusion.py`: Reject substituting prod for staging.
  - `test_target_hallucination.py`: Invented instance IDs rejected.
  - `test_replay_defense.py`: Expired or reused pending tokens rejected.
  - `test_bypass_attempt.py`: Direct calls without guardrail rejected.

### Phase 5 — Functional Streamlit Dashboard
- [ ] Build `dashboard/app.py`:
  - **Overview**: Real KPIs (Total intercepted, allowed, asked, escalated, blocked, latency stats, donut/bar charts) from local `audit.jsonl`.
  - **Interactive Playground**: Real-time agent runner with 5 PRD preset scenarios and custom prompts.
  - **Decision Trace**: Stage-by-stage visual pipeline with measured latencies (User Prompt → Agent → Decider → Policy → Cascade → Execution → Audit).
  - **Audit Log**: Searchable, filterable table with expandable payload inspection and sensitive data redaction.
  - **Evaluation & Benchmarks**: Real evaluation metrics, confusion matrix, and cost/latency comparison.
  - **Configuration**: Active backend, thresholds, endpoints, mock mode indicator.
  - Premium dark-mode security operations center styling.

### Phase 6 — Evaluation Framework & Benchmark
- [ ] Create `eval/cases.jsonl` and `eval/cases.csv` with 120 labeled test cases (30 grounded, 30 ungrounded, 30 injected, 30 ambiguous).
- [ ] Implement `eval/run_benchmark.py`:
  - Compare Tripwire (Decider 2B + Cascade) vs Baseline A (Bedrock LLM Judge directly) vs Baseline B (Deterministic Policy-only).
  - Measure Accuracy, False-Allow rate, False-Block rate, Clarification rate, Escalation rate, P50 & P95 latency, and Cost per 1k calls.
- [ ] Generate real benchmark output in `eval/results/benchmark_report.json` and `eval/results.md`.

### Phase 7 — Reusable Pattern & Standalone Examples
- [ ] Finalize `tripwire_pattern/` as an installable/importable standalone module with its own `README.md`.
- [ ] Build standalone examples in `examples/`:
  - `safe_request.py`
  - `ambiguous_request.py`
  - `unsafe_request.py`
  - `minimal_agent.py`

### Phase 8 — Documentation & Submission Materials
- [ ] Complete root `README.md` with badges, architecture diagram, setup instructions, quickstart, and team credits.
- [ ] Complete `docs/ARCHITECTURE.md` with comprehensive Mermaid diagrams.
- [ ] Complete `docs/SECURITY.md` detailing threat model, attack vectors, fail-closed design, and least-privilege IAM policies.
- [ ] Create `docs/BUILDER_CENTER_ARTICLE.md` (ready for publication on AWS Builder Center).
- [ ] Create `docs/DEMO_SCRIPT.md` (detailed 3-minute video script with timestamps, actions, and spoken narration).
- [ ] Create `docs/HACKATHON_CHECKLIST.md` and `docs/TROUBLESHOOTING.md`.

### Phase 9 — Quality Gates & Verification
- [ ] Run full test suite with `pytest`.
- [ ] Run evaluation benchmark and verify all 120 cases.
- [ ] Launch Streamlit dashboard and test all 5 PRD scenarios.
- [ ] Verify clean git status and zero secret exposure.
