"""Transcript-safe in-memory remediator for legacy ~/.gemini/antigravity/mcp_config.json.

Migrates plaintext API keys from the stale legacy Antigravity MCP config into
Windows Credential Manager (`WinVaultKeyring`, service="antigravity-mcp"),
overwrites secret values with `"__REDACTED_IN_WINVAULT__"`, writes the
redacted archive to `mcp_config.json.deprecated-redacted`, and unlinks the
unredacted file so zero plaintext copies remain on disk.

Transcript safety: NEVER prints or logs raw secret values; outputs only server
names, key names, vault verification booleans, and 8-char SHA-256 fingerprints.

Usage:
    python .agents/scripts/remediate_legacy_mcp.py
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

DEFAULT_SERVICE = "antigravity-mcp"
REDACTED_MARKER = "__REDACTED_IN_WINVAULT__"
_SECRET_PREFIXES = (
    "sk-",
    "ghp_",
    "github_pat_",
    "AIzaSy",
    "GOCSPX-",
    "fc-",
    "tvly-",
)

SECRET_ENV_NAME_RE = re.compile(
    r"(?i)(API[_-]?KEY|TOKEN|SECRET|PASSWORD|API[_-]?HASH|PRIVATE[_-]?KEY|CREDENTIAL)"
)
URL_QUERY_SECRET_RE = re.compile(
    r"([?&](?:[A-Za-z0-9_]*(?:ApiKey|api_key|token|secret|key))=)([^&#\s]+)"
)


def sha256_prefix(val):
    """Return a transcript-safe 8-character SHA-256 fingerprint."""
    digest = hashlib.sha256(val.encode("utf-8", errors="replace")).hexdigest()
    return "sha256:" + digest[:8]


def store_in_vault(service, key_name, secret_val):
    """Store secret_val in OS keyring."""
    import keyring  # type: ignore

    keyring.set_password(service, key_name, secret_val)


def read_from_vault(service, key_name):
    """Read secret_val back from OS keyring to verify persistence."""
    import keyring  # type: ignore

    return keyring.get_password(service, key_name)


def is_secret_env_entry(key_name, val):
    """Return True if an env dict entry represents a credential."""
    if not isinstance(val, str) or not val or val == REDACTED_MARKER:
        return False
    if "NON_SECRET" in key_name.upper():
        return False
    if SECRET_ENV_NAME_RE.search(key_name):
        return True
    return len(val) >= 24 and val.startswith(_SECRET_PREFIXES)


def _persist_and_record_secret(service, server_name, key_name, secret_val, migrated):
    """Store secret_val in vault, verify round-trip, and append transcript-safe metadata."""
    store_in_vault(service, key_name, secret_val)
    if read_from_vault(service, key_name) != secret_val:
        raise RuntimeError(
            "Vault verification failed for key %r (server %r)" % (key_name, server_name)
        )
    migrated.append(
        {
            "server": server_name,
            "key_name": key_name,
            "fingerprint": sha256_prefix(secret_val),
            "vault_service": service,
            "vault_verified": True,
        }
    )


def _remediate_server_env(server_name, server_cfg, service, migrated):
    """Migrate secret env entries in server_cfg['env'] to the OS vault."""
    env_map = server_cfg.get("env")
    if not isinstance(env_map, dict):
        return
    for key_name, val in list(env_map.items()):
        if is_secret_env_entry(key_name, val):
            _persist_and_record_secret(service, server_name, key_name, val, migrated)
            env_map[key_name] = REDACTED_MARKER


def _remediate_server_urls(server_name, server_cfg, service, migrated):
    """Migrate secret query parameters in server_cfg URL fields to the OS vault."""
    for url_field in ("url", "serverUrl"):
        url_val = server_cfg.get(url_field)
        if not isinstance(url_val, str) or not URL_QUERY_SECRET_RE.search(url_val):
            continue

        def _replace_query_secret(match):
            prefix, raw_secret = match.group(1), match.group(2)
            q_key = prefix.lstrip("?&").rstrip("=")
            if raw_secret != REDACTED_MARKER:
                _persist_and_record_secret(
                    service, server_name, q_key, raw_secret, migrated
                )
            return prefix + REDACTED_MARKER

        server_cfg[url_field] = URL_QUERY_SECRET_RE.sub(_replace_query_secret, url_val)


def remediate_config_file(config_path, service=DEFAULT_SERVICE):
    """Migrate secrets to OS vault, write .deprecated-redacted file, and unlink original."""
    path = Path(config_path)
    redacted_path = path.with_name(path.name + ".deprecated-redacted")

    if not path.is_file():
        status = "already_remediated" if redacted_path.is_file() else "not_found"
        return {
            "status": status,
            "redacted_path": str(redacted_path),
            "migrated_keys": [],
        }

    data = json.loads(path.read_bytes().decode("utf-8"))
    servers = data.get("mcpServers", {})
    migrated = []

    for server_name, server_cfg in servers.items():
        if isinstance(server_cfg, dict):
            _remediate_server_env(server_name, server_cfg, service, migrated)
            _remediate_server_urls(server_name, server_cfg, service, migrated)

    redacted_bytes = (json.dumps(data, indent=2) + "\n").encode("utf-8")
    redacted_path.write_bytes(redacted_bytes)
    path.unlink()

    return {
        "status": "remediated",
        "redacted_path": str(redacted_path),
        "migrated_count": len(migrated),
        "migrated_keys": migrated,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Migrate and redact legacy ~/.gemini/antigravity/mcp_config.json."
    )
    parser.add_argument(
        "--service",
        default=DEFAULT_SERVICE,
        help="OS keyring service name (default: %s)." % DEFAULT_SERVICE,
    )
    args = parser.parse_args()

    default_target = Path.home() / ".gemini" / "antigravity" / "mcp_config.json"
    report = remediate_config_file(default_target, service=args.service)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
