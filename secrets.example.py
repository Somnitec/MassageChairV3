"""
Secrets template — copy to secrets.py and fill in your values.

secrets.py is gitignored, so it's safe to store passwords, API keys, and
specific configuration here.
"""

# Hardware connections
LATTEPANDA_HOST = "lattepanda.local"
LATTEPANDA_USER = "user"
LATTEPANDA_SSH_KEY = None  # or path to private key

CHAIR_MCU_PORT = "tcp:lattepanda.local:7000"  # or "/dev/ttyACM0" if local
CONTROLLER_MCU_PORT = "tcp:lattepanda.local:7001"  # if needed

# Ollama / LLM
OLLAMA_HOST = "http://localhost:11434"  # override if on a different machine

# Dashboard
DASHBOARD_PORT = 8001

# Development / debugging
DEBUG = False
LOG_LEVEL = "INFO"
