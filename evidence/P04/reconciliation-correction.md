# P04 reconciliation correction

- Revision: `9f87d3e`
- `scripts/check-isolation.sh` now starts a labelled owned container and a
  separately named unrelated container, stops/removes only the owned name, and
  verifies the unrelated container remains inspectable.
- `buildInspectArgs` and `buildStopArgs` constrain worker reconciliation to
  install/job/generation labels and an exact container name; no prune operation
  is used.
- Full `make verify` passed. Podman emitted a host-specific warning that the
  one-second stop escalated to SIGKILL; cleanup still preserved the unrelated
  container and left no named check containers behind.
