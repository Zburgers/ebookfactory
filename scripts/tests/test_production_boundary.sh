#!/usr/bin/env bash
set -euo pipefail

node --input-type=module <<'NODE'
import assert from "node:assert/strict";
import { buildProductionPrompt } from "./apps/worker/src/production.ts";
import { buildPiArgs } from "./apps/worker/src/pi.ts";

const context = { project_id: "project-1", run_id: "run-1", brief: { profile: "fiction", promise_or_premise: "A test premise" }, budget: { max_turns: 2 } };
assert(buildProductionPrompt(context).includes("A test premise"));
const args = buildPiArgs({ prompt: "Return a short draft", systemPrompt: "bounded", model: "openai-codex/example" });
for (const flag of ["--no-extensions", "--no-skills", "--no-prompt-templates", "--no-tools", "--no-session", "--mode", "json", "--thinking", "low"]) assert(args.includes(flag));
assert(!args.includes("--tool"));
console.log("production boundary behavior test passed");
NODE
