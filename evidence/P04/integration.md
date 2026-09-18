# P04 integration evidence

- Code revision: `58e1161`
- UTC: 2026-09-18
- Runtime: native rootless Podman 4.9.3, OCI runtime `runc`; `podman info` reported rootless `true`; no sudo or socket mount used
- Image: built locally from `infra/podman/Containerfile`; Alpine base pinned to `sha256:d9e853e87e55526f6b2917df91a2115c36dd7c696a35be12163d44e6e2a4b6bc`; verified job image digest `sha256:ceaa82d7c3272607253bc7426039354aa2677d3078775582501b9a551bf63f87`
- Boundary: non-root `ebook` UID 1000 with rootless `keep-id`, read-only root, private `/tmp` tmpfs with noexec/nosuid/nodev, dropped capabilities, no-new-privileges, `network=none`, memory/CPU/PID limits, labels for install/job/generation, and only a generated workspace bind mount
- Real check: `scripts/check-isolation.sh` passed; the container could write only its private workspace output, could not see a host sentinel or `/home/naki`, and had no usable route (`/proc/net/route` <= 1 line)
- Argument check: `scripts/tests/test_sandbox_args.sh` passed workspace traversal rejection and forbidden mount/privilege checks
- Verification: `make verify` passed, including API/migration/contract/recovery checks, worker module execution, sandbox argument check and the real rootless containment check
- Limitation: artifact symlink/hash/size validation, labelled crash reconciliation, cancellation teardown and unrelated-container preservation remain P04/P08 follow-up work; no full H3/H9 claim is made
