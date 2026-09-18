#!/usr/bin/env bash
set -euo pipefail

node --input-type=module <<'NODE'
import assert from "node:assert/strict";
import { buildPodmanArgs, validateWorkspace } from "./apps/worker/src/sandbox.ts";

assert.equal(validateWorkspace("/tmp/jobs", "/tmp/jobs/one"), "/tmp/jobs/one");
assert.throws(() => validateWorkspace("/tmp/jobs", "/tmp/jobs/../home"));
const args = buildPodmanArgs({
  name: "ebook-factory-job-1-1",
  installId: "install-1",
  jobId: "job-1",
  generation: 1,
  workspace: "/tmp/jobs/one",
  command: ["-c", "true"],
});
for (const forbidden of ["/home", "/run/podman", "--privileged"]) assert(!args.join(" ").includes(forbidden));
assert(args.includes("--network=none"));
assert(args.includes("--read-only"));
assert(args.includes("--userns=keep-id"));
assert(args.includes("--cap-drop=all"));
console.log("sandbox argument behavior test passed");
NODE
