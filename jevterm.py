"""Jev Smart Terminal (jevterm) - Main REPL and Entry Point.

Translates natural language intents into PowerShell commands, validates against
a deterministic blocklist, audits safety via a secondary Jev call, and gates
execution based on risk level.
"""

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import time
import unicodedata
from pathlib import Path
from typing import Dict, Any, Optional

import config
import prompts
import safety
from generator import generate_command
from auditor import audit_command

ANSI_REGEX = re.compile(r"\x1b\[[0-9;]*[mK]")


def strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences from string."""
    return ANSI_REGEX.sub("", text)


def display_width(text: str) -> int:
    """Compute visual character width in monospace terminals."""
    clean = strip_ansi(text)
    return sum(2 if unicodedata.east_asian_width(c) in ("F", "W") else 1 for c in clean)


def pad_box_line(text: str, target_width: int) -> str:
    """Pad a string to exact monospace display width, accounting for ANSI codes."""
    w = display_width(text)
    return text + (" " * max(0, target_width - w))

# ============================================================================
# Design System & TrueColor Styling Tokens
# ============================================================================

def init_terminal() -> None:
    """Enable ANSI escape sequences and UTF-8 output on Windows 10/11."""
    os.system("")
    if sys.platform == "win32":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
            mode = ctypes.c_ulong()
            kernel32.GetConsoleMode(handle, ctypes.byref(mode))
            mode.value |= 0x0004  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
            kernel32.SetConsoleMode(handle, mode)
        except Exception:
            pass
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    if hasattr(sys.stderr, "reconfigure"):
        try:
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

# Initialize console encoding and VT mode immediately upon import
init_terminal()

C_RESET = "\033[0m"
C_BOLD = "\033[1m"
C_DIM = "\033[2m"

# Modern 24-bit TrueColor Palette
C_CYAN = "\033[38;2;86;182;234m"       # Soft electric cyan / primary brand
C_BLUE = "\033[38;2;97;175;239m"       # Syntax blue / path accent
C_PURPLE = "\033[38;2;198;120;221m"   # Refined lavender / badges
C_GREEN = "\033[38;2;152;195;121m"    # Soft emerald green / success & low risk
C_YELLOW = "\033[38;2;229;192;123m"   # Warm amber gold / medium risk & warning
C_RED = "\033[38;2;224;108;117m"      # Vibrant coral red / high risk & errors
C_GRAY = "\033[38;2;92;99;112m"       # Muted slate gray / borders & metadata
C_WHITE = "\033[38;2;220;223;228m"    # Crisp light gray / main text


def shorten_path(path_str: str) -> str:
    """Format file path aesthetically, replacing home directory with ~."""
    try:
        p = Path(path_str).resolve()
        home = Path.home().resolve()
        try:
            rel = p.relative_to(home)
            return f"~\\{rel}" if os.name == "nt" else f"~/{rel}"
        except ValueError:
            return str(p)
    except Exception:
        return path_str


def print_banner() -> None:
    """Render a clean, modern startup card."""
    width = 74
    print(f"{C_GRAY}╭{'─' * width}╮{C_RESET}")
    print(f"{C_GRAY}│{C_RESET}{pad_box_line(f'  {C_CYAN}{C_BOLD}✦ Jev Smart Terminal{C_RESET} {C_PURPLE}v1.13{C_RESET}', width)}{C_GRAY}│{C_RESET}")
    print(f"{C_GRAY}│{C_RESET}{pad_box_line(f'  {C_GRAY}Pure Decision Engine • typesafe/jev-1.13 • Windows PowerShell 5.1+{C_RESET}', width)}{C_GRAY}│{C_RESET}")
    print(f"{C_GRAY}├{'─' * width}┤{C_RESET}")
    print(f"{C_GRAY}│{C_RESET}{pad_box_line(f'  {C_WHITE}Catalog:{C_RESET}   22,195 verified templates   {C_WHITE}Safety:{C_RESET}  Deterministic + Auditor', width)}{C_GRAY}│{C_RESET}")
    print(f"{C_GRAY}│{C_RESET}{pad_box_line(f'  {C_WHITE}Commands:{C_RESET}  Type English intent         {C_WHITE}Bypass:{C_RESET}  /<cmd> or /cd <path>', width)}{C_GRAY}│{C_RESET}")
    print(f"{C_GRAY}│{C_RESET}{pad_box_line(f'  {C_WHITE}Shortcuts:{C_RESET} /history, /clear, /help    {C_WHITE}Exit:{C_RESET}    exit or Ctrl+C', width)}{C_GRAY}│{C_RESET}")
    print(f"{C_GRAY}╰{'─' * width}╯{C_RESET}")
    if not config.OPENROUTER_API_KEY:
        print(f"\n{C_YELLOW}  Notice: OPENROUTER_API_KEY not found. Running in offline/mock mode.{C_RESET}")
        print(f"{C_GRAY}  Place your key in .env to enable live typesafe/jev-1.13 decisions.{C_RESET}\n")
    else:
        print()


def show_help() -> None:
    """Display quick usage reference."""
    print(f"\n{C_CYAN}{C_BOLD}Jev Smart Terminal - Command Guide{C_RESET}")
    print(f"  {C_WHITE}Natural Language:{C_RESET} Type what you want to do (e.g. {C_BLUE}\"show listening ports\"{C_RESET})")
    print(f"  {C_WHITE}/<command>:{C_RESET}       Bypass AI and run raw PowerShell (e.g. {C_BLUE}/Get-Service{C_RESET})")
    print(f"  {C_WHITE}/cd <path>:{C_RESET}       Navigate directories (persists across REPL sessions)")
    print(f"  {C_WHITE}/history:{C_RESET}         Show the last 5 executed commands")
    print(f"  {C_WHITE}/clear, /cls:{C_RESET}     Clear the terminal screen")
    print(f"  {C_WHITE}/help:{C_RESET}            Show this cheat sheet")
    print(f"  {C_WHITE}exit, quit:{C_RESET}       Exit jevterm\n")


def show_recent_history(n: int = 5) -> None:
    """Render recently executed commands in a neat list."""
    history_path = config.HISTORY_FILE
    if not history_path.is_file():
        print(f"{C_GRAY}  No execution history found.{C_RESET}\n")
        return
    try:
        with open(history_path, "r", encoding="utf-8") as f:
            records = json.load(f)
            if not isinstance(records, list) or not records:
                print(f"{C_GRAY}  History is empty.{C_RESET}\n")
                return
            recent = records[-n:]
            print(f"\n{C_CYAN}{C_BOLD}Recent Command History:{C_RESET}")
            for r in recent:
                ts = r.get("timestamp", "")[:19].replace("T", " ")
                cmd = r.get("command") or "(none)"
                ran = f"{C_GREEN}ran{C_RESET}" if r.get("ran") else f"{C_RED}cancelled{C_RESET}"
                risk = r.get("risk", "unknown")
                print(f"  {C_GRAY}{ts}{C_RESET} [{risk.upper()}] ({ran}): {C_WHITE}{cmd}{C_RESET}")
            print()
    except Exception as e:
        print(f"{C_RED}  Failed to read history: {e}{C_RESET}\n")


# ============================================================================
# Audit Logging & Execution Core
# ============================================================================

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
        print(f"{C_GRAY}[Warning: Failed to write to history.json: {e}]{C_RESET}", file=sys.stderr)


UIA_PRIMITIVES_PATH = config.BASE_DIR / "scripts" / "uia_primitives.ps1"


def summarize_open_windows(output_str: str) -> str:
    """Parse JSON list of open windows and return a clear, conversational plain-English summary."""
    try:
        start = output_str.find("[")
        end = output_str.rfind("]")
        if start == -1 or end == -1 or end <= start:
            return "No open application windows were detected on your screen."

        windows = json.loads(output_str[start : end + 1])
        if not isinstance(windows, list) or not windows:
            return "No open application windows were detected on your screen."

        apps = []
        for w in windows:
            name = w.get("name", "").strip()
            proc = w.get("process", "").strip()
            if not name or name in ("Program Manager", "NVIDIA GeForce Overlay"):
                continue
            apps.append((name, proc))

        if not apps:
            return "No active application windows are currently visible on your screen."

        window_descriptions = []
        for name, proc in apps:
            if proc and proc.lower() not in name.lower() and proc != "unknown":
                window_descriptions.append(f"{name} ({proc})")
            else:
                window_descriptions.append(name)

        count = len(window_descriptions)
        if count == 1:
            return f"You currently have 1 open window on your screen: {window_descriptions[0]}."
        elif count == 2:
            return f"You currently have 2 open windows on your screen: {window_descriptions[0]} and {window_descriptions[1]}."
        else:
            first_part = ", ".join(window_descriptions[:-1])
            return f"You currently have {count} open windows on your screen: {first_part}, and {window_descriptions[-1]}."
    except Exception as e:
        return f"Unable to parse open windows summary: {e}"


def execute_powershell(command: str) -> tuple:
    """Execute a command in PowerShell and frame its output cleanly."""
    print(f"{C_GRAY}┌── Output ──────────────────────────────────────────────────────────────────{C_RESET}")
    try:
        # Automatically dot-source UIA primitives if available
        script_prefix = f". '{UIA_PRIMITIVES_PATH}'; " if UIA_PRIMITIVES_PATH.is_file() else ""
        full_command = f"{script_prefix}{command}"

        proc = subprocess.run(
            [config.SHELL_EXECUTABLE] + config.SHELL_ARGS + [full_command],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        has_output = False
        if proc.stdout:
            has_output = True
            for line in proc.stdout.splitlines(keepends=True):
                print(f"{C_GRAY}│{C_RESET} {line}", end="")
            if not proc.stdout.endswith("\n"):
                print()

        if proc.stderr:
            has_output = True
            for line in proc.stderr.splitlines(keepends=True):
                print(f"{C_RED}│ {line}{C_RESET}", end="", file=sys.stderr)
            if not proc.stderr.endswith("\n"):
                print(file=sys.stderr)

        if not has_output:
            print(f"{C_GRAY}│  (Command completed with no console output){C_RESET}")

        status_badge = (
            f"{C_GREEN}✓ Completed  •  Exit 0{C_RESET}"
            if proc.returncode == 0
            else f"{C_RED}✖ Failed  •  Exit {proc.returncode}{C_RESET}"
        )
        print(f"{C_GRAY}└── [{C_RESET}{status_badge}{C_GRAY}] ──────────────────────────────────────────{C_RESET}")
        return proc.returncode, proc.stdout or ""
    except Exception as e:
        print(f"{C_RED}│ Execution error: {e}{C_RESET}", file=sys.stderr)
        print(f"{C_GRAY}└── [{C_RED}✖ Error{C_GRAY}] ──────────────────────────────────────────────────────────{C_RESET}")
        return -1, ""


# ============================================================================
# Pipeline Processor
# ============================================================================

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
        print(f"\n{C_GRAY}╭── {C_YELLOW}⚠ UNABLE TO RESOLVE COMMAND{C_RESET} {C_GRAY}──────────────────────────────────────────{C_RESET}")
        print(f"{C_GRAY}│{C_RESET}  {C_WHITE}Intent:{C_RESET}      {intent}")
        print(f"{C_GRAY}│{C_RESET}  {C_WHITE}Explanation:{C_RESET} {explanation}")
        print(f"{C_GRAY}╰────────────────────────────────────────────────────────────────────────────{C_RESET}\n")
        log_history(intent, None, risk, ran=False, exit_code=None)
        return {
            "command": None,
            "risk": risk,
            "explanation": explanation,
            "ran": False,
            "exit_code": None,
            "blocked_by": "unsupported",
        }

    # Stage 2: Deterministic Safety Layer (No model involved, <0.1ms)
    is_safe, block_reason = safety.check_safety(cmd)
    if not is_safe:
        print(f"\n{C_GRAY}╭── {C_RED}{C_BOLD}✖ BLOCKED BY SAFETY LAYER{C_RESET} {C_GRAY}───────────────────────────────────────{C_RESET}")
        print(f"{C_GRAY}│{C_RESET}  {C_WHITE}Reason:{C_RESET}  {C_RED}{block_reason}{C_RESET}")
        print(f"{C_GRAY}│{C_RESET}  {C_WHITE}Command:{C_RESET} {C_GRAY}{cmd}{C_RESET}")
        print(f"{C_GRAY}╰────────────────────────────────────────────────────────────────────────────{C_RESET}\n")
        log_history(intent, cmd, risk, ran=False, exit_code=None)
        return {
            "command": cmd,
            "risk": risk,
            "explanation": explanation,
            "ran": False,
            "exit_code": None,
            "blocked_by": "safety_layer",
        }

    # Stage 3: Auditor (Secondary Jev decision call for medium & high risk)
    if risk in (config.RISK_MEDIUM, config.RISK_HIGH):
        audit_result = audit_command(cmd, use_mock=use_mock)
        if not audit_result.get("safe", False):
            reason = audit_result.get("reason", "Flagged unsafe by auditor.")
            print(f"\n{C_GRAY}╭── {C_RED}{C_BOLD}✖ BLOCKED BY AUDITOR{C_RESET} {C_GRAY}────────────────────────────────────────────{C_RESET}")
            print(f"{C_GRAY}│{C_RESET}  {C_WHITE}Reason:{C_RESET}  {C_RED}{reason}{C_RESET}")
            print(f"{C_GRAY}│{C_RESET}  {C_WHITE}Command:{C_RESET} {C_GRAY}{cmd}{C_RESET}")
            print(f"{C_GRAY}╰────────────────────────────────────────────────────────────────────────────{C_RESET}\n")
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
    risk_label = {
        config.RISK_LOW: f"{C_GREEN}{C_BOLD}● LOW RISK{C_RESET}",
        config.RISK_MEDIUM: f"{C_YELLOW}{C_BOLD}▲ MEDIUM RISK{C_RESET}",
        config.RISK_HIGH: f"{C_RED}{C_BOLD}◆ HIGH RISK{C_RESET}",
    }.get(risk, f"{C_GRAY}{risk.upper()}{C_RESET}")

    # Render Command Preview Card
    print(f"\n{C_GRAY}╭── {C_CYAN}{C_BOLD}Command Preview{C_RESET} {C_GRAY}──────────────────────────────────────────────────────{C_RESET}")
    print(f"{C_GRAY}│{C_RESET}  {C_WHITE}{C_BOLD}{cmd}{C_RESET}")
    print(f"{C_GRAY}├────────────────────────────────────────────────────────────────────────────{C_RESET}")
    action_str = f"  •  {C_WHITE}{explanation}{C_RESET}" if explanation else ""
    print(f"{C_GRAY}│{C_RESET}  {risk_label}  {C_GRAY}•  ⏱ {elapsed:.2f}s{C_RESET}{action_str}")
    print(f"{C_GRAY}╰────────────────────────────────────────────────────────────────────────────{C_RESET}")

    should_execute = False
    if risk == config.RISK_HIGH:
        print(f"\n{C_RED}{C_BOLD}⚠️  High-Risk Command Detected{C_RESET}")
        print(f"{C_WHITE}This command modifies system state or deletes data.{C_RESET}")
        try:
            confirm = input(f"{C_RED}Type 'yes' to proceed: {C_RESET}").strip()
            print()
            if confirm.lower() == "yes":
                should_execute = True
            else:
                print(f"{C_YELLOW}Command cancelled.{C_RESET}\n")
        except (KeyboardInterrupt, EOFError):
            print(f"\n{C_YELLOW}Cancelled.{C_RESET}\n")
            should_execute = False

    elif risk == config.RISK_MEDIUM:
        try:
            confirm = input(f"\n{C_YELLOW}Press [Enter] to execute, or 'n' to cancel: {C_RESET}").strip()
            print()
            if confirm == "" or confirm.lower() in ("y", "yes"):
                should_execute = True
            else:
                print(f"{C_YELLOW}Command cancelled.{C_RESET}\n")
        except (KeyboardInterrupt, EOFError):
            print(f"\n{C_YELLOW}Cancelled.{C_RESET}\n")
            should_execute = False

    else:  # low risk
        print(f"{C_GREEN}⚡ Executing immediately...{C_RESET}")
        should_execute = True

    exit_code = None
    if should_execute:
        exit_code, stdout_str = execute_powershell(cmd)
        print()

        # Milestone 1: Plain English summary for Get-OpenWindows
        if cmd.strip().startswith("Get-OpenWindows") and exit_code == 0:
            summary = summarize_open_windows(stdout_str)
            print(f"{C_GRAY}╭── {C_CYAN}{C_BOLD}✦ Jev Screen Summary{C_RESET} {C_GRAY}──────────────────────────────────────────────────────{C_RESET}")
            print(f"{C_GRAY}│{C_RESET}  {C_WHITE}{summary}{C_RESET}")
            print(f"{C_GRAY}╰────────────────────────────────────────────────────────────────────────────{C_RESET}\n")

    log_history(intent, cmd, risk, ran=should_execute, exit_code=exit_code)
    return {
        "command": cmd,
        "risk": risk,
        "explanation": explanation,
        "ran": should_execute,
        "exit_code": exit_code,
        "blocked_by": None,
    }


# ============================================================================
# Interactive REPL
# ============================================================================

def repl(use_mock: bool = False) -> None:
    """Run the interactive REPL loop."""
    init_terminal()
    print_banner()

    while True:
        cwd_display = shorten_path(os.getcwd())
        try:
            prompt_str = (
                f"{C_GRAY}╭─{C_RESET} {C_CYAN}{C_BOLD}✦ jev{C_RESET}  {C_BLUE}{cwd_display}{C_RESET}\n"
                f"{C_GRAY}╰─❯{C_RESET} "
            )
            user_input = input(prompt_str).strip()
        except (KeyboardInterrupt, EOFError):
            print(f"\n{C_GRAY}Exiting jevterm. Goodbye!{C_RESET}")
            break

        if not user_input:
            continue

        if user_input.lower() in ("exit", "quit"):
            print(f"{C_GRAY}Exiting jevterm. Goodbye!{C_RESET}")
            break

        # Special built-in helpers
        if user_input.lower() in ("/clear", "/cls", "clear", "cls"):
            os.system("cls" if os.name == "nt" else "clear")
            print_banner()
            continue

        if user_input.lower() in ("/help", "help"):
            show_help()
            continue

        if user_input.lower() in ("/history", "history"):
            show_recent_history()
            continue

        # Raw PowerShell escape hatch: lines starting with '/' (or legacy '!')
        if user_input.startswith(("/", "!")):
            raw_cmd = user_input[1:].strip()
            if not raw_cmd:
                print(f"{C_YELLOW}No command provided after escape character.{C_RESET}\n")
                continue

            # Built-in cd handling so directory changes persist in the REPL
            if raw_cmd.lower().startswith("cd ") or raw_cmd.lower() == "cd":
                target_dir = raw_cmd[3:].strip().strip("\"'") if len(raw_cmd) > 2 else str(Path.home())
                if not target_dir:
                    target_dir = str(Path.home())
                try:
                    target_path = Path(target_dir).expanduser().resolve()
                    os.chdir(target_path)
                    print(f"  {C_CYAN}📁 Working directory:{C_RESET} {C_BLUE}{shorten_path(str(target_path))}{C_RESET}\n")
                    log_history(user_input, raw_cmd, risk="raw", ran=True, exit_code=0)
                    continue
                except Exception as e:
                    print(f"{C_RED}cd error: {e}{C_RESET}\n", file=sys.stderr)
                    log_history(user_input, raw_cmd, risk="raw", ran=False, exit_code=1)
                    continue

            print(f"\n{C_PURPLE}⚡ Raw PowerShell:{C_RESET} {C_WHITE}{raw_cmd}{C_RESET}")
            code, _ = execute_powershell(raw_cmd)
            print()
            log_history(user_input, raw_cmd, risk="raw", ran=True, exit_code=code)
            continue

        # Natural Language Intent
        process_intent(user_input, use_mock=use_mock)


def main() -> None:
    init_terminal()
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
