"""Pure redaction utility, runnable without HA."""
from .metrics import METRICS

REDACTED = "**REDACTED**"
SAFE_OPTIONS = {"scan_interval", "enable_controls"}


def diagnostics_payload(config, options, data, success):
    sensitive = ("host", "token_id", "token_secret", "name")
    secrets = [str(config[k]) for k in sensitive if config.get(k)]

    def scrub(value):
        if isinstance(value, str):
            for secret in secrets:
                value = value.replace(secret, REDACTED)
            return value
        if isinstance(value, dict):
            return {scrub(str(k)): scrub(v) for k, v in value.items()}
        if isinstance(value, list):
            return [scrub(v) for v in value]
        return value

    allow = {m.key for m in METRICS} | {"kind", "node", "vmid", "name", "storage", "available"}
    resources = {group: {key: {k: v for k, v in record.items() if k in allow}
                        for key, record in (data or {}).get(group, {}).items()}
                 for group in ("nodes", "guests", "storage")}
    # Do not serialize unknown config values: future secrets stay private.
    return scrub({"config": {k: REDACTED for k in sensitive},
                  "verify_ssl": config.get("verify_ssl", True),
                  "options": {k: v for k, v in options.items() if k in SAFE_OPTIONS},
                  "last_update_success": success, "resources": resources})
