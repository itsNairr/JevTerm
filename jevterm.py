"""Jev Smart Terminal (jevterm) - Main REPL and Entry Point.

Translates natural language intents into PowerShell commands, validates against
a deterministic blocklist, audits safety via a secondary Jev call, and gates
execution based on risk level.
"""

import argparse
import datetime
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, Any, Optional

import config
import prompts
import safety
from generator import generate_command
from auditor import audit_command

# ANSI Color codes for clean terminal output
RESET = "\033[0m"
BOLD = "\033[1m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
CYAN = "\033[36m"
GRAY = "\033[90m"


def log_history(
    intent: str,
    command: Optional[str],
    risk: str,
    ran: bool,
    exit_code: Optional[int],
) -> None:
    """Append execution record to history.json."""
    record = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "intent": intent,
        "command": command,
        "risk": risk,
        "ran": ran,
        "exit_code": exit_code,
    }

    try:
        history_path = config.HISTORY_FILE
        records = []
        if history_path.is_file():
            try:
                with open(history_path, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    if content:
                        records = json.loads(content)
                        if not isinstance(records, list):
                            records = []
            except Exception:
                records = []

        records.append(record)
        with open(history_path, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2)
    except Exception as e:
        print(f"{GRAY}[Warning: Failed to write to history.json: {e}]{RESET}", file=sys.stderr)


def execute_powershell(command: str) -> int:
    """Execute a command in PowerShell and stream its output."""
    try:
        # Run powershell -NoProfile -Command <command>
        proc = subprocess.run(
            [config.SHELL_EXECUTABLE] + config.SHELL_ARGS + [command],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if proc.stdout:
            print(proc.stdout, end="")
        if proc.stderr:
            print(f"{RED}{proc.stderr}{RESET}", end="", file=sys.stderr)
        return proc.returncode
    except Exception as e:
        print(f"{RED}Execution error: {e}{RESET}", file=sys.stderr)
        return -1


def process_intent(intent: str, use_mock: bool = False, json_only: bool = False) -> Dict[str, Any]:
    """Process a single natural language intent through the 4-stage pipeline.

    Returns:
        Dict containing stage results: {command, risk, explanation, ran, exit_code, blocked_by}
    """
    start_time = time.perf_counter()

    # Stage 1: Generator
    gen_result = generate_command(intent, use_mock=use_mock)
    cmd = gen_result.get("command")
    risk = gen_result.get("risk", config.RISK_HIGH)
    explanation = gen_result.get("explanation", "")

    if json_only:
        print(json.dumps(gen_result, indent=2))
        return {
            "command": cmd,
            "risk": risk,
            "explanation": explanation,
            "ran": False,
            "exit_code": None,
            "blocked_by": None,
        }

    # Case: Intent cannot be expressed as shell command
    if not cmd:
        print(f"{YELLOW}[Jev] Cannot generate shell command:{RESET} {explanation}")
        log_history(intent, None, risk, ran=False, exit_code=None)
        return {
            "command": None,
            "risk": risk,
            "explanation": explanation,
            "ran": False,
            "exit_code": None,
            "blocked_by": "unsupported",
        }

    # Stage 2: Deterministic Safety Layer (No model involved)
    is_safe, block_reason = safety.check_safety(cmd)
    if not is_safe:
        print(f"{RED}{BOLD}[BLOCKED by Safety Layer]{RESET} {block_reason}")
        print(f"{GRAY}Command:{RESET} {cmd}")
        log_history(intent, cmd, risk, ran=False, exit_code=None)
        return {
            "command": cmd,
            "risk": risk,
            "explanation": explanation,
            "ran": False,
            "exit_code": None,
            "blocked_by": "safety_layer",
        }

    # Stage 3: Auditor (Second opinion model call)
    audit_result = audit_command(cmd, use_mock=use_mock)
    if not audit_result.get("safe", False):
        reason = audit_result.get("reason", "Flagged unsafe by auditor.")
        print(f"{RED}{BOLD}[BLOCKED by Auditor]{RESET} {reason}")
        print(f"{GRAY}Command:{RESET} {cmd}")
        log_history(intent, cmd, risk, ran=False, exit_code=None)
        return {
            "command": cmd,
            "risk": risk,
            "explanation": explanation,
            "ran": False,
            "exit_code": None,
            "blocked_by": "auditor",
        }

    # Stage 4: Risk Gate & Confirmation
    elapsed = time.perf_counter() - start_time
    print(f"\n{CYAN}{BOLD}Command:{RESET} {cmd}")
    print(f"{GRAY}Risk:{RESET} [{risk.upper()}]  {GRAY}Elapsed:{RESET} {elapsed:.2f}s")
    if explanation:
        print(f"{GRAY}Action:{RESET} {explanation}")

    should_execute = False
    if risk == config.RISK_HIGH:
        print(f"{RED}{BOLD}Caution:{RESET} High-risk command detected. Modifies system state or deletes data.")
        try:
            confirm = input(f"{RED}Type 'yes' to execute (or anything else to cancel): {RESET}").strip()
            if confirm == "yes":
                should_execute = True
            else:
                print(f"{YELLOW}Command cancelled by user.{RESET}")
        except (KeyboardInterrupt, EOFError):
            print(f"\n{YELLOW}Cancelled.{RESET}")
            should_execute = False

    elif risk == config.RISK_MEDIUM:
        try:
            confirm = input(f"{YELLOW}Press [Enter] to execute, or 'n' to cancel: {RESET}").strip()
            if confirm == "" or confirm.lower() in ("y", "yes"):
                should_execute = True
            else:
                print(f"{YELLOW}Command cancelled by user.{RESET}")
        except (KeyboardInterrupt, EOFError):
            print(f"\n{YELLOW}Cancelled.{RESET}")
            should_execute = False

    else:  # low risk
        print(f"{GREEN}Executing immediately...{RESET}")
        should_execute = True

    exit_code = None
    if should_execute:
        print(f"{GRAY}--- Output ---{RESET}")
        exit_code = execute_powershell(cmd)
        print(f"{GRAY}--------------{RESET}")

    log_history(intent, cmd, risk, ran=should_execute, exit_code=exit_code)
    return {
        "command": cmd,
        "risk": risk,
        "explanation": explanation,
        "ran": should_execute,
        "exit_code": exit_code,
        "blocked_by": None,
    }


def repl(use_mock: bool = False) -> None:
    """Run interactive REPL loop."""
    print(f"{CYAN}{BOLD}=================================================={RESET}")
    print(f"{CYAN}{BOLD}       Jev Smart Terminal (jevterm) v1.0          {RESET}")
    print(f"{CYAN}{BOLD}=================================================={RESET}")
    print(f"OS Target: Windows 10/11 (PowerShell 5.1+)")
    print(f"Safety: Deterministic Blocklist + Jev Auditor")
    if not config.OPENROUTER_API_KEY:
        print(f"{YELLOW}Note: OPENROUTER_API_KEY not set. Running in mock/offline mode.{RESET}")
        print(f"{YELLOW}Place your key in .env or set $env:OPENROUTER_API_KEY for live Jev calls.{RESET}")
    print(f"Type your natural-language intent, or '/<command>' to run raw PowerShell.")
    print(f"Type 'exit' or 'quit' to close.\n")

    while True:
        cwd = os.getcwd()
        try:
            prompt_str = f"{CYAN}{BOLD}jev {GRAY}[{cwd}]{CYAN}> {RESET}"
            user_input = input(prompt_str).strip()
        except (KeyboardInterrupt, EOFError):
            print(f"\n{GRAY}Exiting jevterm. Goodbye!{RESET}")
            break

        if not user_input:
            continue

        if user_input.lower() in ("exit", "quit"):
            print(f"{GRAY}Exiting jevterm. Goodbye!{RESET}")
            break

        # Escape hatch: lines starting with '/' (or legacy '!') run raw in PowerShell
        if user_input.startswith(("/", "!")):
            raw_cmd = user_input[1:].strip()
            if not raw_cmd:
                print(f"{YELLOW}No command provided after escape character.{RESET}")
                continue

            # Built-in cd handling so directory changes persist in the REPL
            if raw_cmd.lower().startswith("cd ") or raw_cmd.lower() == "cd":
                target_dir = raw_cmd[3:].strip().strip("\"'") if len(raw_cmd) > 2 else str(Path.home())
                if not target_dir:
                    target_dir = str(Path.home())
                try:
                    target_path = Path(target_dir).expanduser()
                    os.chdir(target_path)
                    print(f"{GRAY}Directory changed to:{RESET} {os.getcwd()}")
                    log_history(user_input, raw_cmd, risk="raw", ran=True, exit_code=0)
                    continue
                except Exception as e:
                    print(f"{RED}cd error: {e}{RESET}", file=sys.stderr)
                    log_history(user_input, raw_cmd, risk="raw", ran=False, exit_code=1)
                    continue

            print(f"{YELLOW}[Bypass] Running raw PowerShell command:{RESET} {raw_cmd}")
            print(f"{GRAY}--- Output ---{RESET}")
            code = execute_powershell(raw_cmd)
            print(f"{GRAY}--------------{RESET}")
            log_history(user_input, raw_cmd, risk="raw", ran=True, exit_code=code)
            continue

        process_intent(user_input, use_mock=use_mock)
        print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Jev Smart Terminal - Natural Language to PowerShell REPL")
    parser.add_argument("intent", nargs="?", help="Direct intent to execute (single-shot mode)")
    parser.add_argument("--json", action="store_true", help="Output generator JSON only (Milestone 1 acceptance)")
    parser.add_argument("--mock", action="store_true", help="Force offline mock mode for testing")
    args = parser.parse_args()

    use_mock = args.mock or (not config.OPENROUTER_API_KEY)

    if args.intent:
        process_intent(args.intent, use_mock=use_mock, json_only=args.json)
    else:
        repl(use_mock=use_mock)


if __name__ == "__main__":
    main()
