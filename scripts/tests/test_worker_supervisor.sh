#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../.."

node --input-type=module <<'NODE'
import assert from "node:assert/strict";
import http from "node:http";
import { runSupervisor } from "./apps/worker/src/supervisor.ts";

const calls = [];
let claimCount = 0;
let failFirstClaim = true;
let failureReportedResolve;
const failureReported = new Promise((resolve) => { failureReportedResolve = resolve; });
const leaseFixture = (jobId, workerId, generation) => ({
  job_id: jobId,
  task_id: "00000000-0000-4000-8000-000000000010",
  run_id: "00000000-0000-4000-8000-000000000011",
  attempt_id: "00000000-0000-4000-8000-000000000012",
  worker_id: workerId,
  generation,
  cancellation_epoch: 0,
  lease_until: new Date(Date.now() + 3000).toISOString(),
  lease_seconds: 3,
});
const server = http.createServer(async (request, response) => {
  const chunks = [];
  for await (const chunk of request) chunks.push(chunk);
  const body = chunks.length ? JSON.parse(Buffer.concat(chunks).toString()) : {};
  calls.push({ path: request.url, body });
  if (request.url === "/private/worker/claim") {
    if (failFirstClaim) {
      failFirstClaim = false;
      response.writeHead(503, { "content-type": "text/plain" });
      response.end("temporary failure");
      return;
    }
    claimCount += 1;
    response.writeHead(200, { "content-type": "application/json" });
    response.end(JSON.stringify(claimCount <= 2 ? leaseFixture(
      `00000000-0000-4000-8000-00000000001${claimCount}`,
      "worker-1",
      claimCount + 3,
    ) : null));
    return;
  }
  if (request.url === "/private/worker/fail") {
    response.writeHead(200, { "content-type": "application/json" });
    response.end("{}");
    failureReportedResolve();
    return;
  }
  response.writeHead(200, { "content-type": "application/json" });
  response.end("{}");
});

await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
const { port } = server.address();
const controller = new AbortController();
let executions = 0;
const supervisorRun = runSupervisor({
  baseUrl: `http://127.0.0.1:${port}`,
  token: "test-token",
  workerId: "worker-1",
  leaseSeconds: 3,
  pollMs: 5,
  heartbeatMs: 15,
  retryDelayMs: 7,
  signal: controller.signal,
  execute: async () => {
    executions += 1;
    if (executions === 2) throw new Error("execution failed");
    await new Promise((resolve) => setTimeout(resolve, 55));
    return { artifact: "artifact-1" };
  },
});
await failureReported;
controller.abort();
await supervisorRun;
await new Promise((resolve) => server.close(resolve));

assert.equal(executions, 2);
assert.ok(calls.some(({ path }) => path === "/private/worker/heartbeat"));
const completed = calls.find(({ path }) => path === "/private/worker/complete");
assert.deepEqual(completed.body, {
  job_id: "00000000-0000-4000-8000-000000000011",
  worker_id: "worker-1",
  generation: 4,
  result_refs: { artifact: "artifact-1" },
});
const failed = calls.find(({ path }) => path === "/private/worker/fail");
assert.equal(failed.body.job_id, "00000000-0000-4000-8000-000000000012");
assert.equal(failed.body.error_class, "worker_execution_failure");
assert.equal(failed.body.retryable, true);
assert.equal(failed.body.retry_after_seconds, 0.007);
assert.ok(calls.some(({ path }) => path === "/private/worker/claim"));
console.log("worker supervisor lifecycle: ok");

const hangingServer = http.createServer((_request, response) => {
  setTimeout(() => {
    if (!response.writableEnded) {
      response.writeHead(503);
      response.end("delayed failure");
    }
  }, 1000);
});
await new Promise((resolve) => hangingServer.listen(0, "127.0.0.1", resolve));
const hangingController = new AbortController();
setTimeout(() => hangingController.abort(), 10);
const hangingStartedAt = Date.now();
await runSupervisor({
  baseUrl: `http://127.0.0.1:${hangingServer.address().port}`,
  token: "test-token",
  workerId: "worker-hanging",
  pollMs: 5,
  signal: hangingController.signal,
  execute: async () => ({}),
});
const hangingElapsedMs = Date.now() - hangingStartedAt;
await new Promise((resolve) => hangingServer.close(resolve));
assert.ok(hangingElapsedMs < 500, `shutdown waited ${hangingElapsedMs}ms for an in-flight request`);
console.log("worker supervisor request cancellation: ok");

const staleCalls = [];
const staleServer = http.createServer(async (request, response) => {
  const chunks = [];
  for await (const chunk of request) chunks.push(chunk);
  const body = chunks.length ? JSON.parse(Buffer.concat(chunks).toString()) : {};
  staleCalls.push({ path: request.url, body });
  if (request.url === "/private/worker/claim") {
    response.writeHead(200, { "content-type": "application/json" });
    response.end(JSON.stringify(leaseFixture(
      "00000000-0000-4000-8000-000000000001",
      "worker-2",
      2,
    )));
    return;
  }
  if (request.url === "/private/worker/heartbeat") {
    response.writeHead(409, { "content-type": "application/json" });
    response.end(JSON.stringify({ detail: "lease expired" }));
    return;
  }
  response.writeHead(204);
  response.end();
});
await new Promise((resolve) => staleServer.listen(0, "127.0.0.1", resolve));
const staleController = new AbortController();
let executionSawAbort = false;
setTimeout(() => staleController.abort(), 150);
await runSupervisor({
  baseUrl: `http://127.0.0.1:${staleServer.address().port}`,
  token: "test-token",
  workerId: "worker-2",
  pollMs: 5,
  heartbeatMs: 5,
  signal: staleController.signal,
  execute: async (_lease, { signal }) => {
    await new Promise((resolve) => setTimeout(resolve, 30));
    executionSawAbort = signal.aborted;
    return { artifact: "must-not-publish" };
  },
});
await new Promise((resolve) => staleServer.close(resolve));
assert.equal(executionSawAbort, true);
assert.equal(staleCalls.some(({ path }) => path === "/private/worker/complete"), false);
assert.equal(staleCalls.some(({ path }) => path === "/private/worker/fail"), false);

let completeAttempts = 0;
const completeBodies = [];
let retryClaims = 0;
const retryServer = http.createServer(async (request, response) => {
  const chunks = [];
  for await (const chunk of request) chunks.push(chunk);
  const body = chunks.length ? JSON.parse(Buffer.concat(chunks).toString()) : {};
  if (request.url === "/private/worker/claim") {
    retryClaims += 1;
    response.writeHead(200, { "content-type": "application/json" });
    response.end(JSON.stringify(retryClaims === 1 ? leaseFixture(
      "00000000-0000-4000-8000-000000000002",
      "worker-3",
      1,
    ) : null));
    return;
  }
  if (request.url === "/private/worker/complete") {
    completeBodies.push(body);
    completeAttempts += 1;
    if (completeAttempts === 1) {
      response.writeHead(503);
      response.end("temporary completion failure");
      return;
    }
  }
  response.writeHead(204);
  response.end();
});
await new Promise((resolve) => retryServer.listen(0, "127.0.0.1", resolve));
const retryController = new AbortController();
setTimeout(() => retryController.abort(), 100);
await runSupervisor({
  baseUrl: `http://127.0.0.1:${retryServer.address().port}`,
  token: "test-token",
  workerId: "worker-3",
  pollMs: 5,
  retryDelayMs: 5,
  signal: retryController.signal,
  execute: async () => null,
});
await new Promise((resolve) => retryServer.close(resolve));
assert.equal(completeAttempts, 2);
assert.deepEqual(completeBodies[1].result_refs, {});

let abortedCompleteAttempts = 0;
const abortedRetryServer = http.createServer(async (request, response) => {
  if (request.url === "/private/worker/claim") {
    response.writeHead(200, { "content-type": "application/json" });
    response.end(JSON.stringify(leaseFixture(
      "00000000-0000-4000-8000-000000000005",
      "worker-6",
      1,
    )));
    return;
  }
  if (request.url === "/private/worker/complete") {
    abortedCompleteAttempts += 1;
    response.writeHead(503);
    response.end("temporary completion failure");
    return;
  }
  response.writeHead(204);
  response.end();
});
await new Promise((resolve) => abortedRetryServer.listen(0, "127.0.0.1", resolve));
const abortedRetryController = new AbortController();
setTimeout(() => abortedRetryController.abort(), 20);
await runSupervisor({
  baseUrl: `http://127.0.0.1:${abortedRetryServer.address().port}`,
  token: "test-token",
  workerId: "worker-6",
  pollMs: 5,
  retryDelayMs: 50,
  signal: abortedRetryController.signal,
  execute: async () => ({ artifact: "aborted-retry" }),
});
await new Promise((resolve) => abortedRetryServer.close(resolve));
assert.equal(abortedCompleteAttempts, 1);

let failedClaimCount = 0;
const failServer = http.createServer(async (request, response) => {
  if (request.url === "/private/worker/claim") {
    failedClaimCount += 1;
    response.writeHead(200, { "content-type": "application/json" });
    response.end(JSON.stringify(failedClaimCount === 1 ? leaseFixture(
      "00000000-0000-4000-8000-000000000003",
      "worker-4",
      1,
    ) : null));
    return;
  }
  if (request.url === "/private/worker/fail") {
    response.destroy();
    return;
  }
  response.writeHead(204);
  response.end();
});
await new Promise((resolve) => failServer.listen(0, "127.0.0.1", resolve));
const failController = new AbortController();
setTimeout(() => failController.abort(), 100);
await runSupervisor({
  baseUrl: `http://127.0.0.1:${failServer.address().port}`,
  token: "test-token",
  workerId: "worker-4",
  pollMs: 5,
  retryDelayMs: 5,
  signal: failController.signal,
  execute: async () => { throw new Error("worker failed"); },
});
await new Promise((resolve) => failServer.close(resolve));
assert.ok(failedClaimCount >= 2);
console.log("worker supervisor failure paths: ok");

let shutdownFailCalls = 0;
const shutdownServer = http.createServer(async (request, response) => {
  if (request.url === "/private/worker/claim") {
    response.writeHead(200, { "content-type": "application/json" });
    response.end(JSON.stringify(leaseFixture(
      "00000000-0000-4000-8000-000000000004",
      "worker-5",
      1,
    )));
    return;
  }
  if (request.url === "/private/worker/fail") shutdownFailCalls += 1;
  response.writeHead(204);
  response.end();
});
await new Promise((resolve) => shutdownServer.listen(0, "127.0.0.1", resolve));
const shutdownController = new AbortController();
setTimeout(() => shutdownController.abort(), 10);
await runSupervisor({
  baseUrl: `http://127.0.0.1:${shutdownServer.address().port}`,
  token: "test-token",
  workerId: "worker-5",
  pollMs: 5,
  signal: shutdownController.signal,
  execute: async (_lease, { signal }) => new Promise((resolve, reject) => {
    signal.addEventListener("abort", () => reject(new Error("shutdown")), { once: true });
  }),
});
await new Promise((resolve) => shutdownServer.close(resolve));
assert.equal(shutdownFailCalls, 0);
console.log("worker supervisor shutdown behavior: ok");

const preAbortedController = new AbortController();
let preAbortedExecutions = 0;
const preAbortedServer = http.createServer((request, response) => {
  if (request.url === "/private/worker/claim") {
    preAbortedController.abort();
    response.writeHead(200, { "content-type": "application/json" });
    response.end(JSON.stringify(leaseFixture(
      "00000000-0000-4000-8000-000000000006",
      "worker-pre-aborted",
      1,
    )), () => setTimeout(() => preAbortedController.abort(), 0));
    return;
  }
  response.writeHead(204);
  response.end();
});
await new Promise((resolve) => preAbortedServer.listen(0, "127.0.0.1", resolve));
await runSupervisor({
  baseUrl: `http://127.0.0.1:${preAbortedServer.address().port}`,
  token: "test-token",
  workerId: "worker-pre-aborted",
  signal: preAbortedController.signal,
  execute: async () => {
    preAbortedExecutions += 1;
    return {};
  },
});
await new Promise((resolve) => preAbortedServer.close(resolve));
assert.equal(preAbortedExecutions, 0);
console.log("worker supervisor pre-aborted execution guard: ok");
NODE
