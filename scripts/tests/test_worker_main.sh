#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../.."

node --input-type=module <<'NODE'
import assert from "node:assert/strict";
import { runWorkerQueues } from "./apps/worker/src/main.ts";

const signal = new AbortController().signal;
const calls = [];
const execute = () => Promise.resolve({ terminal: true });
const productionExecutorFactory = (options) => {
  calls.push({ queue: "production-factory", workerId: options.workerId });
  return execute;
};
const production = (options) => {
  calls.push({ queue: "production", workerId: options.workerId, execute: options.execute });
  return Promise.resolve("production-stopped");
};
const orchestrator = (options) => {
  calls.push({ queue: "orchestrator", ...options });
  return Promise.resolve("orchestrator-stopped");
};

await runWorkerQueues({
  baseUrl: "http://127.0.0.1:6969",
  token: "worker-token",
  workerId: "worker-1",
  signal,
  productionExecutorFactory,
  productionSupervisor: production,
  orchestratorWorker: orchestrator,
});

assert.deepEqual(calls, [
  {
    queue: "production-factory",
    workerId: "worker-1-production",
  },
  {
    queue: "production",
    workerId: "worker-1-production",
    execute,
  },
  {
    queue: "orchestrator",
    baseUrl: "http://127.0.0.1:6969",
    token: "worker-token",
    workerId: "worker-1-orchestrator",
    signal,
  },
]);
console.log("worker entrypoint queue composition: ok");
NODE
