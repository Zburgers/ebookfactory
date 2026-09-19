import assert from "node:assert/strict";
import test from "node:test";
import { runWorkerQueues } from "../src/main.ts";

test("only the trusted orchestrator queue receives the configured KDP skill", async () => {
  const observed = {};
  await runWorkerQueues({
    baseUrl: "http://api",
    token: "token",
    workerId: "worker-4",
    orchestratorSkillPaths: ["/trusted/kdp-publish"],
    productionSupervisor: async (options) => { observed.production = options; },
    orchestratorWorker: async (options) => { observed.orchestrator = options; },
    productionExecutorFactory: () => async () => {},
  });

  assert.equal(observed.production.orchestratorSkillPaths, undefined);
  assert.deepEqual(observed.orchestrator.skillPaths, ["/trusted/kdp-publish"]);
});
