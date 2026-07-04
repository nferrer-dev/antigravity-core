import os
import sys
import subprocess

harness_path = os.environ.get("HARNESS_NEXUS_PATH")
if not harness_path:
    sys.stderr.write("CRITICAL: HARNESS_NEXUS_PATH environment variable is not set. Harness Nexus is a required dependency for antigravity-core orchestration. Please install harness-nexus globally and set this variable.\n")
    sys.exit(1)

# Ensure the global singleton uses its own virtual environment
venv_python = os.path.join(harness_path, ".venv", "Scripts", "python.exe") if os.name == "nt" else os.path.join(harness_path, ".venv", "bin", "python")

env = os.environ.copy()
env["CONFIG_DIR"] = "./config"

# Pass execution to the global singleton MCP server
try:
    subprocess.run([venv_python, "-m", "harness_nexus.server"], cwd=harness_path, env=env, check=True)
except FileNotFoundError:
    sys.stderr.write(f"CRITICAL: Could not find virtual environment python at {venv_python}. Please ensure harness-nexus is properly installed.\n")
    sys.exit(1)
