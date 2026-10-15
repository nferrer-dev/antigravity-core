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
import hashlib
import os
import subprocess
import sys

DEFAULT_SERVICE = "antigravity-mcp"


def _sha256_prefix(val):
    """Return an 8-hex-char SHA-256 prefix without exposing secret plaintext."""
    return hashlib.sha256(val.encode("utf-8")).hexdigest()[:8]


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


def check_secrets(service, check_keys):
    """Verify whether check_keys exist in the OS keyring without printing values."""
    missing = 0
    for key_name in check_keys:
        val = get_secret(service, key_name)
        if val:
            print("%s: PRESENT (sha256:%s)" % (key_name, _sha256_prefix(val)))
        else:
            print("%s: MISSING" % key_name)
            missing += 1
    return 0 if missing == 0 else 1


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


def run_self_test():
    """Run deterministic in-memory self-tests for keyring injection and fail-closed checks."""
    from unittest import mock

    vault = {("antigravity-mcp", "SELF_TEST_KEY"): "self-test-secret-value-99"}
    with mock.patch(
        __name__ + ".get_secret", side_effect=lambda s, k: vault.get((s, k))
    ):
        env = build_injected_env(
            service="antigravity-mcp",
            env_keys=["SELF_TEST_KEY"],
            base_env={"BASE": "1"},
        )
        if env.get("SELF_TEST_KEY") != "self-test-secret-value-99":
            sys.stderr.write("SELF-TEST FAILED: secret injection mismatch\n")
            return 1
        try:
            build_injected_env(
                service="antigravity-mcp",
                env_keys=["MISSING_KEY"],
                base_env={},
            )
            sys.stderr.write("SELF-TEST FAILED: missing key did not raise RuntimeError\n")
            return 1
        except RuntimeError:
            pass
    print("mcp_keyring_launcher.py self-test: PASS")
    return 0


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
        "--check",
        dest="check_keys",
        action="append",
        default=[],
        metavar="KEY_NAME",
        help="Verify secret readiness in the OS keyring (prints sha256 prefix only).",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run built-in deterministic self-test.",
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

    if args.self_test:
        return run_self_test()

    if args.check_keys:
        return check_secrets(args.service, args.check_keys)

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
