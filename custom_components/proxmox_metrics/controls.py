"""Pure lifecycle definitions and state gating."""
ACTIONS = {
    "start": "Start",
    "shutdown": "Graceful shutdown",
    "stop": "Force stop (disruptive)",
    "reset": "Hard reset (disruptive)",
    "reboot": "Graceful reboot",
}


def actions_for(kind):
    if kind == "qemu":
        return tuple(ACTIONS)
    if kind == "lxc":
        return ("start", "shutdown", "stop", "reboot")
    return ()


def can_press(record, action):
    if not record.get("available") or action not in actions_for(record.get("kind")):
        return False
    status = record.get("status")
    if action == "start":
        return status == "stopped"
    if action in {"stop", "reset"}:
        return status in {"running", "paused"}
    return status == "running"
