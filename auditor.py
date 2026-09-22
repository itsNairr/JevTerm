"""Auditor module for Jev Smart Terminal (jevterm).

Provides a second opinion on PowerShell commands using the Jev model via OpenRouter API.
Evaluates commands for destructive actions, exfiltration, privilege escalation, or unauthorized modifications.
"""

import json
import re
from typing import Dict, Any, Optional
import requests

import config
import prompts

def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    """Extract a JSON object from text, handling potential markdown code fences."""
    text = text.strip()
    if not text:
        return None
    
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(1))
            if isinstance(data, dict):
                return data
        except Exception:
            pass

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            data = json.loads(text[start : end + 1])
            if isinstance(data, dict):
                return data
        except Exception:
            pass

    return None


def _mock_auditor(command: str) -> Dict[str, Any]:
    """Offline mock auditor for testing when API key is not present."""
    cmd_lower = command.lower().strip()

    # Data deletion, recursive removal
    if "remove-item" in cmd_lower and ("-recurse" in cmd_lower or "-force" in cmd_lower or "c:\\" in cmd_lower or "*" in cmd_lower):
        return {
            "safe": False,
            "reason": "Command performs recursive or forced deletion on filesystem paths.",
        }

    # Remote code execution / cradles
    if "iex" in cmd_lower or "invoke-expression" in cmd_lower or "curl" in cmd_lower or "wget" in cmd_lower:
        return {
            "safe": False,
            "reason": "Command involves remote script downloading or dynamic expression execution.",
        }

    # Exfiltration
    if "invoke-restmethod" in cmd_lower or "upload" in cmd_lower or "exfil" in cmd_lower:
        return {
            "safe": False,
            "reason": "Command appears to upload local archives or sensitive data to a remote host.",
        }

    # Root / system path writes
    if "c:\\windows" in cmd_lower or "c:\\program files" in cmd_lower or "hklm" in cmd_lower:
        return {
            "safe": False,
            "reason": "Command targets protected Windows system directories or HKLM registry hives.",
        }

    # Default safe for benign commands
    return {
        "safe": True,
        "reason": "Command does not violate safety policies.",
    }


def audit_command(command: str | None, use_mock: bool = False) -> Dict[str, Any]:
    """Audit a PowerShell command for safety using the secondary Jev model call.

    Args:
        command: The PowerShell command string to audit.
        use_mock: If True or if no API key is set, returns simulated response.

    Returns:
        Dict with keys 'safe' (bool) and 'reason' (str).
    """
    if not command or not command.strip():
        return {
            "safe": False,
            "reason": "Empty command provided.",
        }

    if use_mock or not config.OPENROUTER_API_KEY:
        return _mock_auditor(command)

    headers = {
        "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/typesafe/jevterm",
        "X-Title": "Jev Smart Terminal",
    }

    # Primary Jev Decisions API format on https://openrouter.ai/api/alpha/decisions
    decisions_payload = {
        "model": config.AUDITOR_MODEL,
        "state": command,
        "questions": {
            "safe": {
                "type": "noul",
                "instructions": "Is this PowerShell command acceptable to execute (either immediately or under user confirmation), or is it an unacceptable catastrophic risk?",
                "criteria": {
                    "true": "Safe operations: read-only inspection, normal file creation, or targeted deletion of a specific file in the current working directory that can be safely gated with user confirmation.",
                    "false": "Catastrophic or unacceptable commands: recursive/forced deletions targeting broad paths or drive roots (C:\\, ~, wildcards), formatting disks, HKLM registry tampering, downloading and executing remote code, shutdowns, or credential exfiltration.",
                },
            }
        },
    }

    try:
        resp = requests.post(
            config.DECISIONS_ENDPOINT,
            headers=headers,
            json=decisions_payload,
            timeout=config.REQUEST_TIMEOUT,
        )
        if resp.status_code == 200:
            data = resp.json()
            # Jev answers format: {"answers": {"safe": {"type": "noul", "noul": 0.98}}}
            if "answers" in data and "safe" in data["answers"]:
                safe_info = data["answers"]["safe"]
                noul_prob = float(safe_info.get("noul", 0.0))
                # Threshold for safety: 0.70 or higher
                is_safe = noul_prob >= 0.70
                reason = (
                    f"Audited safe by Jev (confidence: {noul_prob:.0%})."
                    if is_safe
                    else f"Flagged unsafe by Jev auditor (safety confidence: {noul_prob:.0%})."
                )
                return {
                    "safe": is_safe,
                    "reason": reason,
                }
    except Exception as e:
        last_error = str(e)

    # Fail-safe default: when in doubt or on error, mark unsafe
    return {
        "safe": False,
        "reason": "Auditor verification failed. Refusing command execution as safety precaution.",
    }
