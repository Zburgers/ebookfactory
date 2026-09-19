import { delimiter as pathDelimiter } from "node:path";
import { runOrchestratorWorker } from "./orchestrator.ts";
import { createProductionExecutor } from "./runner.ts";
import { runSupervisor } from "./supervisor.ts";

export async function runWorkerQueues({
  baseUrl,
  token,
  workerId,
  orchestratorSkillPaths = [],
  signal,
  productionSupervisor = (options) => runSupervisor(options),
  orchestratorWorker = (options) => runOrchestratorWorker(options),
  productionExecutorFactory = (options) => createProductionExecutor(options),
}) {
  const productionWorkerId = `${workerId}-production`;
  const orchestratorWorkerId = `${workerId}-orchestrator`;
  const executeProduction = productionExecutorFactory({
    baseUrl,
    token,
    workerId: productionWorkerId,
  });

  await Promise.all([
    productionSupervisor({
      baseUrl,
      token,
      workerId: productionWorkerId,
      execute: executeProduction,
      signal,
    }),
    orchestratorWorker({
      baseUrl,
      token,
      workerId: orchestratorWorkerId,
      skillPaths: orchestratorSkillPaths,
      signal,
    }),
  ]);
}

const baseUrl = process.env.EBOOK_FACTORY_API_URL || "http://127.0.0.1:6969";
const token = process.env.EBOOK_FACTORY_WORKER_TOKEN;
const workerId = process.env.EBOOK_FACTORY_WORKER_ID || `orchestrator-${process.pid}`;
const configuredOrchestratorSkills = process.env.EBOOK_FACTORY_ORCHESTRATOR_SKILL_PATHS
  || process.env.EBOOK_FACTORY_ORCHESTRATOR_SKILL_PATH
  || "";
const orchestratorSkillPaths = configuredOrchestratorSkills
  .split(pathDelimiter)
  .map((path) => path.trim())
  .filter(Boolean);
if (process.env.EBOOK_FACTORY_RUN_WORKER === "1") {
  if (!token) throw new Error("EBOOK_FACTORY_WORKER_TOKEN is required");
  const controller = new AbortController();
  process.once("SIGTERM", () => controller.abort());
  process.once("SIGINT", () => controller.abort());
  await runWorkerQueues({ baseUrl, token, workerId, orchestratorSkillPaths, signal: controller.signal });
}
