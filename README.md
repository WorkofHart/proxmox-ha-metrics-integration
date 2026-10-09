# Proxmox VE metrics for Home Assistant

A local-polling custom integration for Proxmox VE 8/9 API-token authentication. Add one config entry per API endpoint (standalone node or cluster endpoint); the integration discovers nodes and their QEMU/LXC guests and polls read-only status. QEMU and LXC lifecycle controls are explicit buttons.

## Install

### With HACS

In HACS, open its menu → **Custom repositories**, add `https://github.com/WorkofHart/proxmox-ha-metrics-integration` as an **Integration**, then select the `v0.1.1b0` release. Download it and restart Home Assistant. The earlier `v0.1.0-alpha` release lacks the manifest version and other HACS metadata; do not select it. This is an early test release, not verified against a live HA/Proxmox setup.

### Manually

Copy `custom_components/proxmox_metrics` into `<HA config>/custom_components/`, restart Home Assistant, then Settings → Devices & services → Add integration → Proxmox Metrics. Enter endpoint URL (prefer `https://node:8006`), API token ID (`user@realm!token-name`), secret, and TLS verification choice. Use a trusted certificate; disabling verification is only for isolated networks with a self-signed certificate.

Configure additional independent endpoints as separate entries. Configure scan interval in integration options (15–900 seconds; default 60). Recorder retains numeric measurement sensors with appropriate units/state classes; availability follows coordinator and per-resource status. Proxmox counters (network bytes) are reported as measurements because API counters can reset at guest restart; do not treat them as monotonic energy/cumulative totals. Entities for newly discovered guests and metrics are added on subsequent polls. Numeric sensors use suitable units and state classes where available.

## Permissions (least privilege)

Create a dedicated non-root service user and API token with privilege separation enabled. For read-only telemetry, grant `PVEAuditor` at `/` (or narrower node paths where practical). For lifecycle buttons, add only these privileges on the specific VM/container paths: `VM.PowerMgmt` on `/vms/<VMID>` for QEMU and `/vms/<CTID>` for LXC. In Proxmox, the built-in `PVEVMAdmin` is broader than necessary; create a custom role containing `VM.PowerMgmt` and combine it with `PVEAuditor`. Assign both user and token at the target path with propagation as needed. Do not grant `Sys.Modify`, `VM.Config.*`, `Datastore.*`, or administrator roles. Check effective permissions in Proxmox; API-token privilege separation means the token cannot exceed the parent user's ACLs, and ACLs must be applied to both identities as required by your PVE version. API token secret is shown once; enter it only through HA's config flow, never in source or logs. Home Assistant's config-entry storage is not necessarily encrypted at rest; protect HA backups and filesystem access.

## Dashboard controls warning

Every discovered QEMU VM receives Start, Graceful shutdown, Force stop, Hard reset, and Graceful reboot buttons. Every LXC receives Start, Graceful shutdown, Force stop, and Graceful reboot buttons (Proxmox has no separate LXC hard-reset API). **Controls are disabled by default in integration options. Force stop and hard reset are additionally disabled by default in Home Assistant's entity registry.** To use them, explicitly enable lifecycle controls in integration options, grant the token `VM.PowerMgmt`, and manually enable any disabled entities you intend to use. Force stop and hard reset are abrupt and can cause data loss; graceful shutdown depends on guest cooperation and may not complete. Restrict dashboard access, label controls clearly, and use a confirmation-capable dashboard card/script before exposing disruptive buttons. Home Assistant button entities themselves do not provide a press-confirmation dialog. Test first on a disposable guest.

## Telemetry and limits

Exports available Proxmox API fields such as CPU fraction (scaled to %), memory/disk bytes, uptime seconds, swap, load average, and network rates when returned. API surfaces vary by node, guest type, storage and PVE release; absent metrics are omitted and failed resource polls retain their entity as unavailable when its record vanishes. This project has not been installed into HA or tested against a live authenticated API token; its local mocked transport tests do not prove compatibility with a particular HA or PVE release.

## Local validation

Run `python3 -m unittest discover -s tests -v` and `python3 -m compileall -q custom_components tests`. HA's `homeassistant` package and `pytest-homeassistant-custom-component` are not vendored; install a compatible HA test environment to run actual config-entry/entity tests and `script.hassfest`.

## Kept local, not committed

The superseded `original-draft/`, downloaded `proxmox-api-reference.js`, Python cache files, local `.env`/keys, and any Home Assistant configuration or databases are intentionally excluded. Never commit API tokens or guest-specific operational data.
