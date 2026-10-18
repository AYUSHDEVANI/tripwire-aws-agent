# Tripwire Troubleshooting Guide

A practical reference for common environment, dependency, and execution issues.

---

## 1. Windows & PowerShell Quick Fixes

### A. PowerShell Execution Policy Error
If running `.ps1` scripts gives an unauthorized access error:
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

### B. Python Encoding Error (`charmap codec can't encode character`)
Windows console defaults to `cp1252` legacy encoding. If terminal output fails on unicode symbols:
```powershell
$env:PYTHONIOENCODING="utf-8"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
```

### C. Module Import Errors (`No module named 'agent'` or `'tripwire_pattern'`)
Always run Python scripts and pytest from the repository root:
```powershell
# In PowerShell:
$env:PYTHONPATH="."
python -m pytest -v

# Or use python -m:
python -m eval.run_benchmark
```

---

## 2. Strands Decider 2B Troubleshooting

### A. Starting the Local Decider Server
Strands Decider 2B runs an HTTP server exposing the System One wire format:
```bash
strands-decider serve --port 8099
```
- By default, Tripwire connects to `http://localhost:8099/v1/systemone`.
- If the server is offline or not started, Tripwire automatically activates its **calibrated deterministic fallback** with zero crashes.

### B. Configuring Custom Endpoint
If running Decider in Docker or a remote VM, set in `.env`:
```env
DECIDER_ENDPOINT=http://127.0.0.1:8099
DECIDER_TIMEOUT_SECONDS=2.0
DECIDER_MOCK_FALLBACK=true
```

---

## 3. Amazon Bedrock & AWS Credentials

### A. Running in Zero-Cost Mock Mode (Default)
Tripwire is engineered to run out of the box with **zero AWS credentials and zero cost**:
```env
TRIPWIRE_MODE=mock
```
In mock mode:
- Tool execution mutates an in-memory dictionary.
- The Bedrock LLM Judge runs a calibrated local evaluator.
- You can test, benchmark, and demonstrate the full dashboard with no active AWS account.

### B. Enabling Live Amazon Bedrock
To use real Bedrock models (Claude 3 Haiku) for planning and escalation:
1. Ensure your AWS credentials are configured:
   ```bash
   aws configure
   ```
2. Verify model access in AWS Console:
   - Go to Amazon Bedrock -> Model Access -> Request access to Anthropic Claude 3 Haiku.
3. Update `.env`:
   ```env
   TRIPWIRE_MODE=live
   AWS_REGION=us-east-1
   BEDROCK_MODEL_ID=anthropic.claude-3-haiku-20240307-v1:0
   BEDROCK_JUDGE_MODEL_ID=anthropic.claude-3-haiku-20240307-v1:0
   ```

---

## 4. Streamlit Dashboard Issues

### A. Port 8501 Already in Use
If another Streamlit instance is running:
```bash
streamlit run dashboard/app.py --server.port 8502
```

### B. Clearing Local Audit History
If you wish to reset dashboard telemetry to zero before a recording:
```powershell
Remove-Item -Path .\data\audit.jsonl -Force -ErrorAction SilentlyContinue
```
Then restart the dashboard.
