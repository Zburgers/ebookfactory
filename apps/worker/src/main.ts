import { runOrchestratorWorker } from "./orchestrator.ts";
import { createProductionExecutor } from "./runner.ts";
import { runSupervisor } from "./supervisor.ts";

export async function runWorkerQueues({
  baseUrl,
  token,
  workerId,
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
      signal,
    }),
  ]);
}

const baseUrl = process.env.EBOOK_FACTORY_API_URL || "http://127.0.0.1:6969";
const token = process.env.EBOOK_FACTORY_WORKER_TOKEN;
const workerId = process.env.EBOOK_FACTORY_WORKER_ID || `orchestrator-${process.pid}`;
if (process.env.EBOOK_FACTORY_RUN_WORKER === "1") {
  if (!token) throw new Error("EBOOK_FACTORY_WORKER_TOKEN is required");
  const controller = new AbortController();
  process.once("SIGTERM", () => controller.abort());
  process.once("SIGINT", () => controller.abort());
  await runWorkerQueues({ baseUrl, token, workerId, signal: controller.signal });
}
