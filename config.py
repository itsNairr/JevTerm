"""Configuration module for Jev Smart Terminal (jevterm).

Handles API endpoint configuration, model identifiers, API key discovery
(from environment or .env file), PowerShell execution settings, and risk thresholds.
"""

import os
from pathlib import Path

# Base directory of the project
BASE_DIR = Path(__file__).resolve().parent

def load_dotenv(env_path: Path = BASE_DIR / ".env") -> None:
    """Simple parser for .env file if present, without external dependencies."""
    if not env_path.is_file():
        return
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip().strip("\"'")
                if key and key not in os.environ:
                    os.environ[key] = val
    except Exception:
        pass

# Automatically load .env if available
load_dotenv()

# OpenRouter Authentication & API Settings
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "").strip()

# Primary OpenRouter Endpoints
DECISIONS_ENDPOINT = os.environ.get(
    "JEVTERM_DECISIONS_ENDPOINT", "https://openrouter.ai/api/alpha/decisions"
)
CHAT_ENDPOINT = os.environ.get(
    "JEVTERM_CHAT_ENDPOINT", "https://openrouter.ai/api/v1/chat/completions"
)

# Pure Jev Pipeline: Both generator and auditor run on TypeSafe Jev 1.13 decisions API
MODEL = "typesafe/jev-1.13"
GENERATOR_MODEL = "typesafe/jev-1.13"
AUDITOR_MODEL = "typesafe/jev-1.13"
ENDPOINT = DECISIONS_ENDPOINT

# tldr + PowerShell command catalog file
CATALOG_FILE = BASE_DIR / "catalog.json"

# HTTP Request Timeout (seconds)
REQUEST_TIMEOUT = float(os.environ.get("JEVTERM_TIMEOUT", "15.0"))

# Target OS and Shell
SHELL_EXECUTABLE = "powershell"
SHELL_ARGS = ["-NoProfile", "-Command"]

# Risk Level Constants
RISK_LOW = "low"
RISK_MEDIUM = "medium"
RISK_HIGH = "high"
VALID_RISKS = {RISK_LOW, RISK_MEDIUM, RISK_HIGH}

# History file path
HISTORY_FILE = BASE_DIR / "history.json"
