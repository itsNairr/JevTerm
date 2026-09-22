# Jev Smart Terminal

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![OS: Windows 10/11](https://img.shields.io/badge/OS-Windows%2010%20%2F%2011-0078D6.svg)](https://www.microsoft.com/windows)
[![Shell: PowerShell 5.1+](https://img.shields.io/badge/shell-PowerShell%205.1%2B-5391FE.svg)](https://learn.microsoft.com/powershell/)
[![Model: TypeSafe Jev 1.13](https://img.shields.io/badge/model-TypeSafe%20Jev%201.13-brightgreen.svg)](https://openrouter.ai/)
[![Decisions API: OpenRouter Alpha](https://img.shields.io/badge/API-OpenRouter%20Decisions-orange.svg)](https://openrouter.ai/api/alpha/decisions)

A high-performance natural-language-to-PowerShell terminal REPL designed for Windows 10/11. Built entirely on **TypeSafe Jev 1.13 decisions** (`POST https://openrouter.ai/api/alpha/decisions`) paired with an indexed **22,181-command `tldr-pages` template catalog**, a zero-model deterministic regex blocklist, and tiered execution gates.

> **Core Philosophy**: Jev never touches the operating system directly. It decides, your code acts. Zero generative hallucinations, zero prompt drift.

---

## The Paradigm: Decision Models vs. Generative LLMs

Traditional natural-language terminal assistants rely on generative chat completions, waiting for streaming text output while risking hallucinated parameters, non-existent cmdlets, or prompt injections.

`jevterm` takes an engineering-first, decision-centric approach:

| Architectural Dimension | Generative Chat LLM Approach | `jevterm` (TypeSafe Jev Decisions) |
|---|---|---|
| **Command Generation** | Generates raw text syntax token-by-token | Routes intent to pre-tested templates from 22,181 verified entries |
| **Execution Latency** | Dependent on multi-token generation speed | Measured sub-second execution (399.7ms median P50, 504.6ms avg) |
| **Injection Resilience** | Vulnerable to prompt injection yielding raw executable strings | Constrained strictly to selecting approved catalog template IDs |
| **Pricing Model** | Standard chat completion input + output token rates | Atomic decisions at $0.042 / 1M prompt tokens (output tokens free on Decisions API) |

---

## Architecture & Multi-Layer Safety Model

```
               User Input (Intent or /raw)
                            │
              ┌─────────────┴─────────────┐
              │ Starts with '/'           │ Regular NL Intent
              ▼                           ▼
      Raw PowerShell Execution    Stage 1: Jev Command Router (choice)
      (Bypasses AI translation)   Jev 1.13 selects from 22,181 templates
                                  Returns: {command, risk, explanation}
                                          │
                                          ▼
                                  Stage 2: Deterministic Safety Layer
                                  Zero-model regex/substring blocklist (<1ms, 0.70ms avg)
                                  [BLOCKED if matched]
                                          │
                                          ▼
                                  Stage 3: Fast-Path & Auditor (noul)
                                  ├── Low Risk   ──► Bypasses auditor (Fast-Path)
                                  └── Med/High   ──► Jev 1.13 noul safety audit
                                          │
                                          ▼
                                  Stage 4: Execution Gate
                                  ├── Low Risk   ──► Executes immediately
                                  ├── Medium Risk──► Requires [Enter] / 'y' confirmation
                                  └── High Risk  ──► Requires explicitly typed 'yes'
                                          │
                                          ▼
                                  PowerShell Execution Engine
                                  `powershell -NoProfile -Command ...`
                                          │
                                          ▼
                                  Audit Trail (`history.json`)
```

---

## Key Features

- **100% Pure Jev Pipeline**: Both command selection (`choice`) and safety auditing (`noul`) run natively on `typesafe/jev-1.13` via OpenRouter's Decisions API. No third-party LLMs or chat completions.
- **22,181 Pre-Tested Command Templates**: Sourced directly from `tldr-pages` (Windows + developer CLI tools), Windows app launchers, and native PowerShell cmdlets.
- **Sub-Second Execution (~504ms Average)**: Fast in-memory candidate retrieval combined with atomic Jev decisions and persistent HTTP keep-alive connection pooling.
- **Deterministic Backstop (`safety.py`)**: Instant regex/substring blocklist that unconditionally vetoes drive wipes, format commands, remote code execution cradles, and registry attacks regardless of model output (<1ms).
- **Modern Aesthetic Terminal UI**: TrueColor styling, rounded unicode preview cards, two-line prompt with path shortening (`~\Desktop`), and framed execution output streaming with exit pills.
- **App & Web Launchers**: Seamlessly opens apps and sites (`open gemini`, `open whatsapp`, `open word`, `open excel`, `open spotify`, `open calc`) via Windows `Start-Process`.
- **Dynamic CWD Prompt & `/` Escape Hatch**: Shows current working directory in the prompt with built-in `/cd <path>` navigation, `/history`, `/clear`, and `/` raw command execution.
- **Dynamic Parameter Slot-Filling**: Injects target filenames (e.g. `this.py`), folder names, and flags directly into matched templates, while stripping un-provided optional placeholders.

---

## Project Structure

```
NLPTerminal/
├── jevterm.py          # REPL loop, aesthetic cards, dynamic CWD prompt, / escape hatch, execution
├── generator.py        # 100% Jev choice command router over catalog
├── auditor.py          # 100% Jev noul safety auditor
├── safety.py           # Deterministic zero-model regex blocklist (<1ms)
├── prompts.py          # Jev decision criteria and schemas
├── config.py           # Endpoint, model IDs, catalog path, and key loading
├── catalog.json        # 22,181 verified command templates extracted from tldr-pages + Windows cmdlets
├── history.json        # Append-only execution audit log
├── benchmark.py        # Automated live latency, throughput, and decision benchmarking suite
├── README.md           # Documentation, safety model, and latency specs
├── .env / .env.example # API key configuration (protected by .gitignore)
├── .gitignore          # Ignores .env and Python cache
└── tests/              # Unit and adversarial test suites
    ├── test_safety.py
    └── test_adversarial.py
```

---

## Risk Classification

- **`low`**: Read-only inspection (e.g., `Get-Location`, `Get-PSDrive`, `Get-ChildItem`, `Get-Process`). Executes immediately.
- **`medium`**: Writing or creating files in the current working directory. Requires pressing `[Enter]` or typing `y` to confirm.
- **`high`**: Deletions, overwrites, system-wide changes, package updates, or privilege escalation. Requires explicitly typing `yes`.

---

## Deterministic Blocklist (`safety.py`)

Regardless of user phrasing or model confidence, the deterministic layer unconditionally blocks:
- Recursive or forced deletes targeting drive roots (`C:\`), home (`~`, `$HOME`, `$env:USERPROFILE`), or broad wildcards.
- Legacy forced deletions (`del /f /s /q`, `rd /s /q`).
- Disk formatting and partitioning (`Format-Volume`, `format c:`, `diskpart`, `Clear-Disk`).
- Registry modifications under `HKLM:` (`reg delete`, `Remove-Item HKLM:`, `Set-ItemProperty HKLM:`).
- Download-and-execute cradles (`IEX` / `Invoke-Expression` with `Invoke-WebRequest`, `curl | sh`, `irm | iex`).
- Machine shutdown or reboot (`shutdown`, `Restart-Computer`, `Stop-Computer`).
- Writes to `C:\Windows` or `C:\Program Files`.
- Disabling security posture (`Set-ExecutionPolicy Unrestricted`, disabling Defender monitoring).
- Ownership or ACL takeovers (`takeown`, `icacls`).

---

## Installation & Setup

### Requirements
- **OS**: Windows 10 or 11
- **PowerShell**: 5.1 or later
- **Python**: 3.10+
- **Dependencies**: `pip install requests`

### API Key Configuration
Create a `.env` file in the project root:
```env
OPENROUTER_API_KEY=sk-or-v1-your-openrouter-key-here
```
*(The `.env` file is already listed in `.gitignore` to prevent accidental credential leakage).*

Alternatively, set as an environment variable in PowerShell:
```powershell
$env:OPENROUTER_API_KEY = "sk-or-v1-your-openrouter-key-here"
```

---

## Usage

### Interactive REPL
Launch the terminal:
```powershell
python jevterm.py
```

Inside the REPL:
```powershell
jev [C:\Users\harik\Desktop\NLPTerminal]> show disk usage
jev [C:\Users\harik\Desktop\NLPTerminal]> what folder are you in
jev [C:\Users\harik\Desktop\NLPTerminal]> list all python files modified in the last day
jev [C:\Users\harik\Desktop\NLPTerminal]> open text.py in vscode
jev [C:\Users\harik\Desktop\NLPTerminal]> /Get-Service | Where-Object Status -eq 'Running'   # '/' runs raw PowerShell
jev [C:\Users\harik\Desktop\NLPTerminal]> /cd ..                                            # change directory
jev [C:\Users\harik\Desktop]> exit
```

### Single-Shot Mode
```powershell
python jevterm.py "show disk usage"
python jevterm.py "list all python files modified in the last day" --json
```

---

## Empirical Benchmark & Performance Metrics

Benchmarked live on Windows 11 running against the live `typesafe/jev-1.13` decision endpoint on OpenRouter with TLS connection pooling (`benchmark.py`):

### 1. Latency Distribution (Live Measurements)

| Pipeline Stage | Metric Measured | Min | Median (P50) | Average | P95 |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **Catalog Search & Ranking** | In-memory keyword/synonym match across 22k items | 55.7 ms | 98.9 ms | **102.8 ms** | 180.9 ms |
| **Deterministic Safety Layer** | Zero-model regex/substring rule evaluation | 0.001 ms | 0.068 ms | **0.70 ms** | 12.7 ms |
| **Jev 1.13 Command Router** | Single atomic `choice` decision via API | 314.8 ms | 408.3 ms | **502.5 ms** | 1,772.3 ms |
| **Fast-Path End-to-End** | Low-risk read-only commands (Router + Safety) | **315.0 ms** | **399.7 ms** | **504.6 ms** | 1,772.3 ms |
| **Audited-Path End-to-End** | Med/High-risk commands (Router + Safety + Auditor) | 1,890.6 ms | 1,890.6 ms | **1,890.6 ms** | 1,890.6 ms |

### 2. Operational & Cost Characteristics (Measured & Official API Rates)

- **Inference Latency**: Fast-path commands resolve in **399.7 ms** (median P50) and **504.6 ms** (average) against the live OpenRouter endpoint.
- **Inference Cost**: OpenRouter list rate for `typesafe/jev-1.13` is **$0.042 per 1M prompt tokens**, with **$0.00 output token cost** on the Decisions API. With an average prompt payload of ~240 tokens per decision, the API cost is approximately **$0.00001 per command** (~100,000 commands per $1.00).
- **Structural Syntax Guarantee**: Because Jev selects an existing verified catalog template ID rather than generating free-form shell syntax token-by-token, syntax errors from invented cmdlets or invalid flags are eliminated by design.
- **Deterministic Backstop**: Every command is evaluated against an unconditional regex/substring blocklist in an average of **0.70 ms** prior to execution.

### 3. Security & Safety Evaluation

- **Unit Safety Suite (`tests/test_safety.py`)**: **9/9 Passed (100%)** in 0.008s
- **Adversarial Security Suite (`tests/test_adversarial.py`)**: **10/10 Passed (100%)**
  - Blocked mass deletion, drive root wipes, home directory destruction
  - Blocked IEX piped download-and-execute cradles
  - Blocked data exfiltration and credential theft attempts
  - Enforced typed `yes` confirmation for targeted deletions and package upgrades
