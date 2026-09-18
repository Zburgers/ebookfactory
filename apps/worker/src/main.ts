import { runOrchestratorWorker } from "./orchestrator.ts";

const baseUrl = process.env.EBOOK_FACTORY_API_URL || "http://127.0.0.1:6969";
const token = process.env.EBOOK_FACTORY_WORKER_TOKEN;
const workerId = process.env.EBOOK_FACTORY_WORKER_ID || `orchestrator-${process.pid}`;
if (process.env.EBOOK_FACTORY_RUN_WORKER === "1") {
  if (!token) throw new Error("EBOOK_FACTORY_WORKER_TOKEN is required");
  const controller = new AbortController();
  process.once("SIGTERM", () => controller.abort());
  process.once("SIGINT", () => controller.abort());
  await runOrchestratorWorker({ baseUrl, token, workerId, signal: controller.signal });
}
