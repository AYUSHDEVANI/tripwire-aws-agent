# AWS Strands Decider Hackathon Submission Checklist

**Event**: Strands Decider Agent Hackathon  
**Submission Window**: October 16 – October 23, 2026 (Submissions close 11:59 PM PT)  
**Required Tags**: `#strands-decider-2b` and `#guardrails`  
**Team Credits**: Ayush (Agent & Decider), Abhishek (Eval & Dashboard), Team Lead (Integrator & Submitter)

---

## 1. Deliverables Status Matrix

| Deliverable | Requirement | Status | Notes |
| :--- | :--- | :--- | :--- |
| **1. Working Agent** | Built with Strands Agents SDK, Decider 2B integration, mock AWS tools, zero-cost mode | **COMPLETED & TESTED** | `agent/`, `tripwire_pattern/`, 28/28 pytest passing |
| **2. Public GitHub Repository** | Clean repo, MIT License, architecture diagram, setup instructions, reusable pattern | **COMPLETED IN WORKSPACE** | Needs manual git push to your public GitHub remote |
| **3. Reusable Pattern** | `tripwire_pattern/` folder with `question.py`, `handler.py`, `cascade.py`, `README.md` | **COMPLETED** | Fully importable in 3 lines of code |
| **4. Benchmark Framework** | 120 labeled cases, comparison against LLM Judge and Policy baselines | **COMPLETED & MEASURED** | 100% Accuracy, 0% False Allow, report in `eval/results.md` |
| **5. Streamlit Ops Dashboard** | Telemetry, playground, decision trace, redacted audit logs, benchmark charts | **COMPLETED & TESTED** | `dashboard/app.py` runs with `streamlit run dashboard/app.py` |
| **6. Builder Center Article** | Article covering problem, Decider 2B, cascade, results, and reproduction | **DRAFTED & POLISHED** | Draft ready at `docs/BUILDER_CENTER_ARTICLE.md`. Needs manual publishing on builder.aws.com |
| **7. Demo Video** | Video under 3 minutes, public on YouTube, covering all 5 PRD scenarios | **SCRIPTED & TIMED** | Script at `docs/DEMO_SCRIPT.md` (2m 45s). Needs screen recording & YouTube upload |
| **8. Mandatory Tags** | `#strands-decider-2b` and `#guardrails` | **PREPARED** | Included in README, article, and submission metadata |

---

## 2. Action Items for Final Submission

### A. What Is Completed & Verified in Code
1. Full end-to-end Strands Agent with InterventionHandler interception lifecycle.
2. 4-lane Decision Cascade (ALLOW, ASK, ESCALATE, BLOCK) with calibrated confidence routing.
3. In-memory mock AWS environment with safe state transitions.
4. Comprehensive 28-test automated suite (unit, integration, security).
5. 120 labeled test cases evaluated across three comparative architectures.
6. Full Streamlit SecOps dashboard with real data and Plotly charts.
7. Secret-redacting JSONL audit logger.
8. Complete documentation suite (`ARCHITECTURE.md`, `SECURITY.md`, `DEMO_SCRIPT.md`, `BUILDER_CENTER_ARTICLE.md`).

### B. What Requires Your Manual Action (Submission Steps)
1. **Push Repository to GitHub**:
   ```bash
   git init
   git add .
   git commit -m "Initial release: Tripwire Decision Cascade for Safe AWS Agents"
   git remote add origin https://github.com/<your-username>/tripwire-aws-agent.git
   git push -u origin main
   ```
2. **Publish Article on AWS Builder Center**:
   - Log into [builder.aws.com](https://builder.aws.com) with your AWS Builder ID.
   - Copy the draft from `docs/BUILDER_CENTER_ARTICLE.md`.
   - Publish with tags: `#strands-decider-2b` and `#guardrails`.
   - Copy the published article URL.
3. **Record and Upload Demo Video**:
   - Follow the timing and shot list in `docs/DEMO_SCRIPT.md`.
   - Record screen and voiceover (under 2m 50s).
   - Upload to YouTube as **Public** (or unlisted). Ensure no copyrighted music or logos.
4. **Submit Devpost Entry**:
   - Fill in project name: `Tripwire — Decision Cascade for Safe AWS Agents`.
   - Paste GitHub repository URL.
   - Paste YouTube video URL.
   - Paste Builder Center article URL.
   - Ensure tags `#strands-decider-2b` and `#guardrails` are attached.
   - Submit before October 23, 11:59 PM PT.
