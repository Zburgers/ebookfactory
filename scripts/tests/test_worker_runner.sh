#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../.."

node --input-type=module <<'NODE'
import assert from "node:assert/strict";
import http from "node:http";
import { EventEmitter } from "node:events";
import { createProductionExecutor } from "./apps/worker/src/runner.ts";
import { runPiProduction } from "./apps/worker/src/production.ts";
import { runSupervisor } from "./apps/worker/src/supervisor.ts";
import { createOrchestratorExecutor } from "./apps/worker/src/orchestrator.ts";

const lease = {
  job_id: "00000000-0000-4000-8000-000000000101",
  task_id: "00000000-0000-4000-8000-000000000102",
  run_id: "00000000-0000-4000-8000-000000000103",
  attempt_id: "00000000-0000-4000-8000-000000000104",
  worker_id: "runner-test",
  generation: 7,
  cancellation_epoch: 0,
  lease_until: new Date(Date.now() + 3000).toISOString(),
  lease_seconds: 3,
};
const context = { project_id: "project-from-api", run_id: lease.run_id, brief: { title: "A real draft" }, budget: { max_tokens: 1000 } };
const calls = [];
const server = http.createServer(async (request, response) => {
  const chunks = [];
  for await (const chunk of request) chunks.push(chunk);
  const body = chunks.length ? JSON.parse(Buffer.concat(chunks).toString()) : null;
  calls.push({ path: request.url, headers: request.headers, body });
  if (request.url === "/private/worker/claim") return json(response, lease);
  if (request.url === `/private/worker/jobs/${lease.job_id}/context`) return json(response, context);
  if (request.url === "/private/worker/providers") return json(response, [{ provider: "openai-codex", scope: "app", protocol: "pi-native", orchestration_model: "gpt-5.6-luna", drafting_model: "gpt-5.6-luna", review_model: "gpt-5.6-luna", credential_configured: true }]);
  if (request.url === "/private/worker/production-result") return json(response, { accepted: true }, 204);
  if (request.url === "/private/worker/heartbeat") return json(response, {}, 204);
  if (request.url === "/private/worker/complete") return json(response, { unexpected: true });
  return json(response, { detail: "not found" }, 404);
});

function json(response, value, status = 200) {
  response.writeHead(status, { "content-type": "application/json" });
  response.end(status === 204 ? "" : JSON.stringify(value));
}

await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
const baseUrl = `http://127.0.0.1:${server.address().port}`;
let piArgs;
const execute = createProductionExecutor({
  baseUrl,
  token: "worker-token",
  workerId: lease.worker_id,
  provider: "openai-codex",
  runProduction: async ({ context: receivedContext, model }) => {
    piArgs = { receivedContext, model };
    return { text: "draft text", provider: "openai-codex", model, callId: "call-123", usage: { input_tokens: 11, output_tokens: 22 } };
  },
});
const controller = new AbortController();
setTimeout(() => controller.abort(), 500);
await runSupervisor({ baseUrl, token: "worker-token", workerId: lease.worker_id, execute, pollMs: 5, heartbeatMs: 20, signal: controller.signal });
await new Promise((resolve) => server.close(resolve));

assert.deepEqual(piArgs, { receivedContext: context, model: "gpt-5.6-luna" });
const productionResult = calls.find(({ path }) => path === "/private/worker/production-result");
assert.deepEqual(productionResult.body, {
  job_id: lease.job_id, worker_id: lease.worker_id, generation: lease.generation,
  content: "draft text", provider: "openai-codex", model: "gpt-5.6-luna", call_id: "call-123",
  usage: { input_tokens: 11, output_tokens: 22 },
});
assert.equal(productionResult.headers["x-ebook-worker-token"], "worker-token");
assert.equal(calls.some(({ path }) => path === "/private/worker/complete"), false);
assert.equal(calls.find(({ path }) => path.includes("/context")).headers["x-worker-id"], lease.worker_id);
assert.equal(calls.find(({ path }) => path.includes("/context")).headers["x-generation"], String(lease.generation));
console.log("worker runner production-result boundary: ok");

let orchestratorResult;
const orchestratorServer = http.createServer(async (request, response) => {
  const chunks = [];
  for await (const chunk of request) chunks.push(chunk);
  const body = chunks.length ? JSON.parse(Buffer.concat(chunks).toString()) : null;
  if (request.url.includes("/context")) return json(response, { project_id: "p", messages: [{ role: "user", content: "hello" }] });
  if (request.url === "/private/worker/providers") return json(response, [{ provider: "openai-codex", scope: "app", protocol: "pi-native", orchestration_model: "openai-codex/gpt-5.6-luna" }]);
  if (request.url === "/private/orchestrator/result") { orchestratorResult = body; return json(response, {}, 204); }
  return json(response, {}, 404);
});
await new Promise((resolve) => orchestratorServer.listen(0, "127.0.0.1", resolve));
const orchestratorExecute = createOrchestratorExecutor({
  baseUrl: `http://127.0.0.1:${orchestratorServer.address().port}`, token: "worker-token", workerId: "pi-1",
  runProduction: async ({ context: receivedContext, model }) => ({ text: `answer:${receivedContext.messages[0].content}`, provider: "openai-codex", model: "gpt-5.6-luna", callId: "turn-call", usage: { input_tokens: 2, output_tokens: 3 } }),
});
await orchestratorExecute({ turn_id: "turn-1", generation: 2 }, {});
await new Promise((resolve) => orchestratorServer.close(resolve));
assert.deepEqual(orchestratorResult, { turn_id: "turn-1", worker_id: "pi-1", generation: 2, content: "answer:hello", provider: "openai-codex", model: "openai-codex/gpt-5.6-luna", call_id: "turn-call", usage: { input_tokens: 2, output_tokens: 3 } });
console.log("orchestrator Pi adapter/result boundary: ok");

let abortedRequests = 0;
const alreadyAbortedServer = http.createServer((_request, response) => {
  abortedRequests += 1;
  response.writeHead(200);
  response.end("{}");
});
await new Promise((resolve) => alreadyAbortedServer.listen(0, "127.0.0.1", resolve));
const alreadyAborted = new AbortController();
alreadyAborted.abort();
const alreadyAbortedExecute = createProductionExecutor({
  baseUrl: `http://127.0.0.1:${alreadyAbortedServer.address().port}`,
  token: "token",
  workerId: "worker",
});
await assert.rejects(() => alreadyAbortedExecute(lease, { signal: alreadyAborted.signal }), /abort/i);
await new Promise((resolve) => alreadyAbortedServer.close(resolve));
assert.equal(abortedRequests, 0);
console.log("worker runner pre-aborted signal: ok");

let qualifiedResult;
const qualifiedServer = http.createServer(async (request, response) => {
  const chunks = [];
  for await (const chunk of request) chunks.push(chunk);
  const body = chunks.length ? JSON.parse(Buffer.concat(chunks).toString()) : null;
  if (request.url.includes("/context")) return json(response, context);
  if (request.url === "/private/worker/providers") {
    return json(response, [{ provider: "openai-codex", scope: "app", protocol: "pi-native", orchestration_model: "openai-codex/gpt-5.6-luna" }]);
  }
  if (request.url === "/private/worker/production-result") {
    qualifiedResult = body;
    return json(response, {}, 204);
  }
  return json(response, {}, 204);
});
await new Promise((resolve) => qualifiedServer.listen(0, "127.0.0.1", resolve));
const qualifiedExecute = createProductionExecutor({
  baseUrl: `http://127.0.0.1:${qualifiedServer.address().port}`,
  token: "token",
  workerId: lease.worker_id,
  runProduction: async ({ model }) => ({
    text: "qualified draft",
    provider: "openai-codex",
    model: "gpt-5.6-luna",
    callId: "qualified-call",
  }),
});
await qualifiedExecute(lease, {});
await new Promise((resolve) => qualifiedServer.close(resolve));
assert.equal(qualifiedResult.model, "openai-codex/gpt-5.6-luna");
console.log("worker runner qualified provider model attribution: ok");

const invalidServer = http.createServer((request, response) => {
  response.writeHead(request.url === "/providers" ? 200 : 200, { "content-type": "application/json" });
  response.end(request.url === "/private/worker/providers" ? JSON.stringify([{ provider: "other", scope: "app", protocol: "pi-native" }]) : "not-json");
});
await new Promise((resolve) => invalidServer.listen(0, "127.0.0.1", resolve));
const invalidBaseUrl = `http://127.0.0.1:${invalidServer.address().port}`;
const invalidExecute = createProductionExecutor({ baseUrl: invalidBaseUrl, token: "token", workerId: "worker", provider: "openai-codex", runProduction: async () => ({}) });
await assert.rejects(() => invalidExecute(lease, {}), /configured provider|malformed/i);
await new Promise((resolve) => invalidServer.close(resolve));
console.log("worker runner configuration and malformed response errors: ok");

const child = new EventEmitter();
child.stdout = new EventEmitter();
child.stderr = new EventEmitter();
child.killCalls = 0;
child.kill = () => { child.killCalls += 1; child.emit("close", null); return true; };
const childController = new AbortController();
const production = runPiProduction({
  context,
  model: "gpt-5.6-luna",
  signal: childController.signal,
  spawnProcess: () => child,
});
childController.abort();
await assert.rejects(() => production, /aborted|cancelled/i);
assert.equal(child.killCalls, 1);
console.log("Pi production cancellation: ok");

let oversizedHeartbeat = false;
const oversizedServer = http.createServer((request, response) => {
  if (request.url === "/private/worker/claim") return json(response, lease);
  if (request.url === "/private/worker/heartbeat") {
    oversizedHeartbeat = true;
    response.writeHead(200, { "content-type": "application/json" });
    response.end("x".repeat(64 * 1024 + 1));
    return;
  }
  response.writeHead(204);
  response.end();
});
await new Promise((resolve) => oversizedServer.listen(0, "127.0.0.1", resolve));
const oversizedController = new AbortController();
setTimeout(() => oversizedController.abort(), 80);
await runSupervisor({ baseUrl: `http://127.0.0.1:${oversizedServer.address().port}`, token: "token", workerId: "runner-test", pollMs: 5, heartbeatMs: 5, signal: oversizedController.signal, execute: async () => new Promise(() => {}) });
await new Promise((resolve) => oversizedServer.close(resolve));
assert.equal(oversizedHeartbeat, true);
console.log("worker supervisor bounded heartbeat response: ok");

const hungServer = http.createServer((request, response) => {
  if (request.url === "/private/worker/claim") return json(response, lease);
  if (request.url === "/private/worker/heartbeat") return;
  response.writeHead(204);
  response.end();
});
await new Promise((resolve) => hungServer.listen(0, "127.0.0.1", resolve));
const hungController = new AbortController();
setTimeout(() => hungController.abort(), 80);
await runSupervisor({ baseUrl: `http://127.0.0.1:${hungServer.address().port}`, token: "token", workerId: "runner-test", pollMs: 5, heartbeatMs: 5, requestTimeoutMs: 10, signal: hungController.signal, execute: async () => new Promise(() => {}) });
await new Promise((resolve) => hungServer.close(resolve));
console.log("worker supervisor hung heartbeat timeout: ok");

const timeoutServer = http.createServer((_request, _response) => {});
await new Promise((resolve) => timeoutServer.listen(0, "127.0.0.1", resolve));
const timeoutExecute = createProductionExecutor({
  baseUrl: `http://127.0.0.1:${timeoutServer.address().port}`,
  token: "token",
  workerId: "runner-test",
  requestTimeoutMs: 10,
});
await assert.rejects(
  () => Promise.race([
    timeoutExecute(lease, {}),
    new Promise((_, reject) => setTimeout(() => reject(new Error("runner timeout regression")), 500)),
  ]),
  /timed out|timeout|aborted/i,
);
await new Promise((resolve) => timeoutServer.close(resolve));
console.log("worker runner request timeout: ok");

const oversizedChild = new EventEmitter();
oversizedChild.stdout = new EventEmitter();
oversizedChild.stderr = new EventEmitter();
oversizedChild.killCalls = 0;
oversizedChild.kill = () => { oversizedChild.killCalls += 1; oversizedChild.emit("close", null); return true; };
const oversizedProduction = runPiProduction({ context, model: "gpt-5.6-luna", spawnProcess: () => oversizedChild });
oversizedChild.stdout.emit("data", Buffer.alloc(1024 * 1024 + 1, "x"));
await assert.rejects(() => oversizedProduction, /output limit|exceeded/i);
assert.equal(oversizedChild.killCalls, 1);
console.log("Pi production output bound: ok");
NODE
