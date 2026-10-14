"""OS Credential Manager (WinVaultKeyring) launcher for MCP stdio servers.

Resolves secret environment variable names from the OS credential store
(Windows Credential Locker via `keyring`) into the child process environment
before launching the target MCP server with direct `stdin`/`stdout`/`stderr`
file-descriptor inheritance.

Direct stdio passthrough guarantees zero mutation of JSON-RPC `Content-Length`
headers and avoids Windows pipe chunk-boundary deadlocks.

Usage:
    # Store a secret interactively (reads from getpass/stdin without echoing):
    python .agents/scripts/mcp_keyring_launcher.py --set OPENAI_API_KEY

    # Launch an MCP server with secrets injected from WinVaultKeyring:
    python .agents/scripts/mcp_keyring_launcher.py --env OPENAI_API_KEY -- npx -y some-mcp
"""
import argparse
import getpass
import os
import subprocess
import sys

DEFAULT_SERVICE = "antigravity-mcp"


def get_secret(service, key_name):
    """Retrieve a secret from the OS keyring."""
    import keyring  # type: ignore

    return keyring.get_password(service, key_name)


def set_secret(service, key_name, secret_value):
    """Store a secret in the OS keyring."""
    import keyring  # type: ignore

    keyring.set_password(service, key_name, secret_value)


def build_injected_env(service, env_keys, base_env=None):
    """Return a copy of base_env with env_keys populated from the OS keyring.

    Raises RuntimeError (fail-closed) if any requested key is missing or empty.
    """
    env = dict(os.environ if base_env is None else base_env)
    for key_name in env_keys:
        val = get_secret(service, key_name)
        if not val:
            raise RuntimeError(
                "Missing required secret %r in OS keyring (service=%r)"
                % (key_name, service)
            )
        env[key_name] = val
    return env


def run_with_keyring(service, env_keys, command, base_env=None):
    """Inject secrets from keyring and execute command with direct stdio inheritance."""
    if not command:
        raise ValueError("No target command specified after '--'")
    env = build_injected_env(service=service, env_keys=env_keys, base_env=base_env)
    completed = subprocess.run(
        command,
        env=env,
        stdin=None,
        stdout=None,
        stderr=None,
        check=False,
    )
    return completed.returncode


def main(argv=None):
    raw_args = list(sys.argv[1:] if argv is None else argv)
    cmd_part = []
    if "--" in raw_args:
        sep_idx = raw_args.index("--")
        cmd_part = raw_args[sep_idx + 1 :]
        raw_args = raw_args[:sep_idx]

    parser = argparse.ArgumentParser(
        description="Launch MCP servers with secrets injected from OS Credential Manager."
    )
    parser.add_argument(
        "--service",
        default=DEFAULT_SERVICE,
        help="Keyring service namespace (default: %s)." % DEFAULT_SERVICE,
    )
    parser.add_argument(
        "--set",
        dest="set_key",
        metavar="KEY_NAME",
        help="Interactively store a secret in the OS keyring.",
    )
    parser.add_argument(
        "--env",
        dest="env_keys",
        action="append",
        default=[],
        metavar="KEY_NAME",
        help="Environment variable name to inject from the OS keyring (repeatable).",
    )
    args = parser.parse_args(raw_args)

    if args.set_key:
        val = getpass.getpass("Enter secret value for %s (%s): " % (args.set_key, args.service))
        if not val:
            sys.stderr.write("Aborted: empty secret value.\n")
            return 1
        set_secret(args.service, args.set_key, val)
        print("Stored %s in OS keyring (service=%s)." % (args.set_key, args.service))
        return 0

    if not cmd_part:
        sys.stderr.write("Error: missing target command after '--'.\n")
        return 1

    try:
        return run_with_keyring(
            service=args.service,
            env_keys=args.env_keys,
            command=cmd_part,
        )
    except Exception as exc:
        sys.stderr.write("mcp_keyring_launcher error: %s\n" % exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
