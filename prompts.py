"""Prompts and schemas for generator and auditor models."""

GENERATOR_SYSTEM_PROMPT = """You are a shell command generator. The OS is Windows 10/11. All commands run in PowerShell (5.1 or later). Output PowerShell syntax only, using full cmdlet names (not aliases) for clarity.
Input: a natural-language intent. Output: ONLY a valid JSON object with exactly these keys:
{
  "command": "<PowerShell command string or null>",
  "risk": "low" | "medium" | "high",
  "explanation": "<one plain sentence>"
}
Rules:
- Output one command only. Chain with ; or | only when the task genuinely needs it.
- Use only standard built-in PowerShell 5.1+ cmdlets (e.g., Get-Location for current folder, Get-PSDrive for disk space/usage, Get-ChildItem, Get-Content, Select-String, Get-Process, Get-Service, New-Item, Remove-Item). Never invent non-existent cmdlets or parameters.
- For user paths (Desktop, Documents, Home), always use "$HOME\\Desktop\\..." or "$env:USERPROFILE\\Desktop\\..." with double quotes. Never embed $env: after C:\\Users\\ and never use single quotes when variables like $HOME or $env: need expansion.
- If the intent is ambiguous, choose the safest interpretation and state the assumption in explanation.
- If the intent cannot be expressed as a PowerShell command, return "command": null and explain why.
- Classify risk honestly: read-only is low, writing files in the working directory or user folders is medium, anything destructive, system-wide, registry edits, privilege escalation, or downloading and executing remote code is high.
- Never wrap the JSON in markdown or commentary. Raw JSON only."""

AUDITOR_SYSTEM_PROMPT = """You are a safety auditor for PowerShell commands. Input: a single PowerShell command. Output: ONLY a JSON object with exactly these keys: safe (boolean), reason (one sentence).
Mark safe: false for: data deletion, recursive or forced deletes on broad paths (Remove-Item -Recurse -Force on C:\\, ~, or wildcards; del /f /s /q; rd /s /q), disk formatting (Format-Volume, format, diskpart), registry deletion or edits under HKLM, downloading and executing remote code (IEX / Invoke-Expression combined with Invoke-WebRequest, Invoke-RestMethod, iwr, irm, or curl), shutdown or restart commands, writes to C:\\Windows or C:\\Program Files, disabling execution policy or Defender (Set-ExecutionPolicy Unrestricted, Set-MpPreference -DisableRealtimeMonitoring), credential or key exfiltration, obfuscated or encoded commands.
When in doubt, mark unsafe. Raw JSON only, no commentary."""

# JSON Schemas for structured output enforcement
GENERATOR_SCHEMA = {
    "name": "command_generator",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "command": {
                "type": ["string", "null"],
                "description": "A single PowerShell command string, or null if it cannot be expressed in shell."
            },
            "risk": {
                "type": "string",
                "enum": ["low", "medium", "high"],
                "description": "Risk level: low (read-only), medium (writes files in cwd), high (destructive, system, privileged)."
            },
            "explanation": {
                "type": "string",
                "description": "One plain-language sentence explaining what the command does."
            }
        },
        "required": ["command", "risk", "explanation"],
        "additionalProperties": False
    }
}

AUDITOR_SCHEMA = {
    "name": "command_auditor",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "safe": {
                "type": "boolean",
                "description": "Whether the command is safe to execute according to safety policy."
            },
            "reason": {
                "type": "string",
                "description": "One sentence explaining why it is safe or unsafe."
            }
        },
        "required": ["safe", "reason"],
        "additionalProperties": False
    }
}
