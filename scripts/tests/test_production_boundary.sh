#!/usr/bin/env bash
set -euo pipefail

node --input-type=module <<'NODE'
import assert from "node:assert/strict";
import { buildProductionPrompt } from "./apps/worker/src/production.ts";
import { buildPiArgs, parsePiEvent } from "./apps/worker/src/pi.ts";
import { buildCodexArtTurn, buildCodexInitialize, buildCodexThreadStart, parseCodexArtEvent } from "./apps/worker/src/codex-art.ts";
import { parseCodexRateLimits } from "./apps/worker/src/quota.ts";

const context = { project_id: "project-1", run_id: "run-1", brief: { profile: "fiction", promise_or_premise: "A test premise" }, budget: { max_turns: 2 } };
assert(buildProductionPrompt(context).includes("A test premise"));
const args = buildPiArgs({ prompt: "Return a short draft", systemPrompt: "bounded", model: "openai-codex/example" });
for (const flag of ["--no-extensions", "--no-skills", "--no-prompt-templates", "--no-tools", "--no-session", "--mode", "json", "--thinking", "low"]) assert(args.includes(flag));
assert(!args.includes("--tool"));
assert.equal(parsePiEvent(JSON.stringify({ type: "message_end", message: { role: "assistant", content: [{ type: "text", text: "A " }, { type: "text", text: "draft" }] } })).text, "A draft");
assert.equal(parsePiEvent(JSON.stringify({ type: "message_update", assistantMessageEvent: { type: "text_delta", delta: "duplicate me" } })).text, "");
assert.equal(parsePiEvent(JSON.stringify({ type: "message_end", message: { role: "assistant", content: [{ type: "text", text: "final draft" }] } })).text, "final draft");
assert.equal(buildCodexInitialize().method, "initialize");
assert.equal(buildCodexThreadStart("gpt-5.6-luna").params.model, "gpt-5.6-luna");
assert.equal(buildCodexArtTurn("thread-1", "make a cover").params.input[0].text, "make a cover");
assert.equal(parseCodexArtEvent(JSON.stringify({ params: { item: { type: "imageGeneration", status: "completed", savedPath: "/tmp/cover.png" } } })).savedPath, "/tmp/cover.png");
const quota = parseCodexRateLimits({ rateLimits: { rateLimitsByLimitId: { primary: { usedPercent: 29, windowDurationMins: 300, resetsAt: 1789766594 }, secondary: { usedPercent: 26, windowDurationMins: 10080, resetsAt: 1789805318 } }, planType: "plus" } }, new Date("2026-09-19T00:00:00Z"));
assert.equal(quota.length, 2);
assert.equal(quota[0].account_alias, "subscription");
assert.equal(quota[0].remaining, 71);
assert.equal(quota[0].plan_label, "plus");
assert(!Object.values(quota[0]).some((value) => String(value).includes("accountId")));
const unavailable = parseCodexRateLimits({ rateLimits: { rateLimitsByLimitId: { credits: { balance: "0", hasCredits: false } }, planType: "plus" } });
assert.equal(unavailable[0].capability_state, "unavailable");
assert.equal(unavailable[0].bucket, "unavailable");
assert(!unavailable[0].bucket.includes("unknown"));
console.log("production boundary behavior test passed");
NODE
