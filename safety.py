"""Deterministic safety layer for PowerShell commands.

This layer uses case-insensitive regular expressions and substring checks to block
known dangerous patterns regardless of model output. It acts as an absolute backstop:
if any pattern matches, the command is BLOCKED immediately.
"""

import re
from typing import Tuple, List, Dict

# Blocklist definition: list of dicts with regex pattern, human-readable description, and rule category
DANGEROUS_PATTERNS: List[Dict[str, str]] = [
    # 1. Remove-Item / rmdir / rm with -Recurse / -r targeting drive roots, home, or wildcards
    {
        "pattern": r"(?i)\b(?:Remove-Item|del|rmdir|rd|erase|rm)\b.*?(?:-(?:Recurse|r)\b.*?(?:[c-zC-Z]:[\\/]|~|\$HOME|\$env:USERPROFILE|\*|\.\*)|(?:[c-zC-Z]:[\\/]|~|\$HOME|\$env:USERPROFILE|\*|\.\*).*?-(?:Recurse|r)\b)",
        "reason": "Recursive delete targeting root, home directory, or broad wildcard",
    },
    {
        "pattern": r"(?i)\b(?:Remove-Item|del|rmdir|rd|erase|rm)\b.*?(?:[c-zC-Z]:[\\/]|~|\$HOME|\$env:USERPROFILE|\*|\.\*).*?-(?:Force|-f\b)",
        "reason": "Forced deletion targeting root, home directory, or wildcard",
    },

    # 2. Legacy cmd deletion flags (del /f /s /q, rd /s /q, erase /f /s /q) targeting roots or wildcards
    {
        "pattern": r"(?i)\b(?:del|erase)\b.*?(?:\/f|\/s|\/q).*?(?:[c-zC-Z]:[\\/]|~|%USERPROFILE%|\*|\.\.)",
        "reason": "Forced quiet recursive deletion of drive roots or wildcards",
    },
    {
        "pattern": r"(?i)\b(?:rd|rmdir)\b.*?(?:\/s|\/q).*?(?:[c-zC-Z]:[\\/]|~|%USERPROFILE%|\*|\.\.)",
        "reason": "Forced quiet directory removal of root or broad paths",
    },

    # 3. Disk formatting and partitioning
    {
        "pattern": r"(?i)\bFormat-Volume\b",
        "reason": "Disk formatting command (Format-Volume)",
    },
    {
        "pattern": r"(?i)\bformat\s+[a-zA-Z]:",
        "reason": "Drive format command (format [drive]:)",
    },
    {
        "pattern": r"(?i)\bdiskpart\b",
        "reason": "Disk partitioning utility (diskpart)",
    },
    {
        "pattern": r"(?i)\bClear-Disk\b",
        "reason": "Disk wipe command (Clear-Disk)",
    },

    # 4. Registry tampering under HKLM
    {
        "pattern": r"(?i)\breg\s+delete\b",
        "reason": "Direct registry deletion (reg delete)",
    },
    {
        "pattern": r"(?i)\b(?:Remove-Item|Remove-ItemProperty|Clear-Item|Clear-ItemProperty)\s+.*?\bHKLM:",
        "reason": "Registry deletion under HKLM drive",
    },
    {
        "pattern": r"(?i)\b(?:Set-ItemProperty|New-ItemProperty|Rename-ItemProperty)\s+.*?\bHKLM:",
        "reason": "Registry modification under HKLM drive",
    },
    {
        "pattern": r"(?i)\b(?:HKEY_LOCAL_MACHINE)\b.*?(?:delete|remove|clear)",
        "reason": "HKEY_LOCAL_MACHINE registry modification/deletion",
    },

    # 5. Remote code execution idioms (download-and-execute)
    {
        "pattern": r"(?i)\b(?:iex|Invoke-Expression)\s*\(?\s*(?:&|Invoke-WebRequest|Invoke-RestMethod|iwr|irm|curl|wget)\b",
        "reason": "Download-and-execute cradle (Invoke-Expression with web request)",
    },
    {
        "pattern": r"(?i)\b(?:Invoke-WebRequest|Invoke-RestMethod|iwr|irm|curl|wget)\b.*?\|\s*(?:iex|Invoke-Expression)\b",
        "reason": "Piped download-and-execute cradle (web request piped to IEX)",
    },
    {
        "pattern": r"(?i)\b(?:iex|Invoke-Expression)\b.*?(?:http[s]?://|ftp://)",
        "reason": "Direct expression execution of remote URL payload",
    },
    {
        "pattern": r"(?i)\b(?:curl|wget)\b.*?\|\s*(?:sh|bash|powershell|cmd)\b",
        "reason": "Piped remote script execution into shell interpreter",
    },

    # 6. System reboot and shutdown
    {
        "pattern": r"(?i)\b(?:shutdown|Restart-Computer|Stop-Computer)\b",
        "reason": "System shutdown or restart command",
    },
    {
        "pattern": r"(?i)\bshutdown\.exe\s+.*?[/-][srt]",
        "reason": "System shutdown utility call",
    },

    # 7. Modifying or writing to Windows or Program Files system directories
    {
        "pattern": r"(?i)\b(?:Out-File|Set-Content|Add-Content|New-Item|Copy-Item|Move-Item|Remove-Item)\b.*?(?:[c-zC-Z]:\\Windows\b|\$env:WINDIR\b|\$env:SystemRoot\b)",
        "reason": "Targeting system Windows directory for writes or removals",
    },
    {
        "pattern": r"(?i)\b(?:Out-File|Set-Content|Add-Content|New-Item|Copy-Item|Move-Item|Remove-Item)\b.*?(?:[c-zC-Z]:\\Program Files\b|\$env:ProgramFiles\b)",
        "reason": "Targeting Program Files directory for writes or removals",
    },
    {
        "pattern": r"(?i)(?:>|>>)\s*(?:[c-zC-Z]:\\Windows\b|[c-zC-Z]:\\Program Files\b)",
        "reason": "Redirection write into Windows or Program Files directory",
    },

    # 8. Disabling Defender or security posture
    {
        "pattern": r"(?i)\bSet-ExecutionPolicy\s+(?:Unrestricted|Bypass)\b",
        "reason": "Disabling PowerShell script execution policy",
    },
    {
        "pattern": r"(?i)\bSet-MpPreference\b.*?-DisableRealtimeMonitoring\s+\$true\b",
        "reason": "Disabling Windows Defender real-time monitoring",
    },
    {
        "pattern": r"(?i)\b(?:Stop-Service|Set-Service)\s+.*?(?:WinDefend|MpsSvc|wuauserv)\b",
        "reason": "Stopping or modifying critical Windows security services",
    },

    # 9. Ownership takeover / ACL tampering on system paths
    {
        "pattern": r"(?i)\btakeown\b.*?(?:[c-zC-Z]:\\Windows|[c-zC-Z]:\\System32|\/f\s+[c-zC-Z]:)",
        "reason": "Takeown command targeting system directories or drives",
    },
    {
        "pattern": r"(?i)\bicacls\b.*?(?:[c-zC-Z]:\\Windows|[c-zC-Z]:\\System32|\/grant.*?[Ff])",
        "reason": "ACL modification grant on system paths",
    },

    # 10. Obfuscated or Base64-encoded execution
    {
        "pattern": r"(?i)\bpowershell(?:\.exe)?\s+.*?(?:-enc|-encodedcommand)\b",
        "reason": "Encoded PowerShell command execution (obfuscation vector)",
    },
]


def check_safety(command: str | None) -> Tuple[bool, str | None]:
    """Check a PowerShell command against the deterministic blocklist.

    Args:
        command: The PowerShell command string to evaluate.

    Returns:
        A tuple of (is_safe: bool, block_reason: str | None).
        If unsafe, is_safe is False and block_reason contains the explanation.
    """
    if not command or not command.strip():
        return False, "Empty or null command"

    cmd = command.strip()

    # Iterate through all paranoid patterns
    for item in DANGEROUS_PATTERNS:
        pattern = item["pattern"]
        if re.search(pattern, cmd):
            return False, f"BLOCKED by safety layer: {item['reason']}"

    return True, None
