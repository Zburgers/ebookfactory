/** Bounded host Pi runner; durable job fencing remains owned by the API. */

import { spawn } from "node:child_process";
import { randomUUID } from "node:crypto";
import { buildPiArgs, parsePiEvent } from "./pi.ts";

const SYSTEM_PROMPT =
  "You are a bounded ebook production worker. Return only useful manuscript text. " +
  "Do not approve work, invoke tools, access files, or change project state.";
const MAX_OUTPUT_BYTES = 1024 * 1024;

export function buildProductionPrompt(context) {
  if (!context?.project_id || ( !Array.isArray(context.messages) && (!context?.run_id || !context?.brief))) throw new Error("incomplete production context");
  if (Array.isArray(context.messages)) {
    return [
      "You are the Ebook Factory dashboard orchestrator. Answer the user's latest message directly.",
      "Use the conversation context, do not invoke tools, and do not claim work was performed unless it was.",
      JSON.stringify({ project_id: context.project_id, messages: context.messages }),
    ].join("\n\n");
  }
  return [
    "Create the next bounded manuscript draft from this approved brief.",
    "Preserve the requested profile, audience, language, length range and output formats.",
    "Return a concise title followed by section headings and complete prose.",
    JSON.stringify({ project_id: context.project_id, run_id: context.run_id, brief: context.brief, budget: context.budget }),
  ].join("\n\n");
}

export function runPiProduction({ context, model, command = "pi", signal, spawnProcess = spawn }) {
  const callId = randomUUID();
  const args = buildPiArgs({ prompt: buildProductionPrompt(context), systemPrompt: SYSTEM_PROMPT, model, thinking: "low" });
  return new Promise((resolve, reject) => {
    const child = spawnProcess(command, args, { stdio: ["ignore", "pipe", "pipe"], shell: false });
    const events = [];
    let stdout = "";
    let stderr = "";
    let outputBytes = 0;
    let settled = false;
    let killTimer;
    const cleanup = () => {
      signal?.removeEventListener("abort", abort);
      if (killTimer) clearTimeout(killTimer);
      child.stdout.removeListener("data", onStdout);
      child.stderr.removeListener("data", onStderr);
      child.removeListener("error", onError);
      child.removeListener("close", onClose);
    };
    const settleReject = (error) => {
      if (settled) return;
      settled = true;
      cleanup();
      reject(error);
    };
    const abort = () => {
      if (settled) return;
      child.kill("SIGTERM");
      settleReject(new Error("Pi production aborted"));
      killTimer = setTimeout(() => child.kill("SIGKILL"), 250);
    };
    const rejectOutputLimit = () => {
      if (settled) return;
      settleReject(new Error("Pi production output limit exceeded"));
      child.kill("SIGTERM");
      killTimer = setTimeout(() => child.kill("SIGKILL"), 250);
    };
    const onStdout = (chunk) => {
      if (settled || signal?.aborted) return;
      const textChunk = chunk.toString();
      outputBytes += Buffer.byteLength(textChunk);
      if (outputBytes > MAX_OUTPUT_BYTES) return rejectOutputLimit();
      stdout += textChunk;
      for (const line of stdout.split("\n").slice(0, -1)) {
        const event = parsePiEvent(line);
        if (event) events.push(event);
      }
      stdout = stdout.split("\n").at(-1) || "";
    };
    const onStderr = (chunk) => { if (!settled) stderr = `${stderr}${chunk}`.slice(-1000); };
    const onError = (error) => settleReject(error);
    const onClose = (code) => {
      if (settled || signal?.aborted) return settleReject(new Error("Pi production aborted"));
      if (code !== 0) return settleReject(new Error(`Pi production exited with code ${code}: ${stderr.replaceAll(/\s+/g, " ").trim()}`));
      const text = events.map((event) => event.text).filter(Boolean).join("\n").trim();
      if (!text) return settleReject(new Error("Pi production returned no manuscript text"));
      if (Buffer.byteLength(text) > MAX_OUTPUT_BYTES) return rejectOutputLimit();
      const finalEvent = [...events].reverse().find((event) => event.usage || event.model || event.provider);
      const usage = finalEvent?.usage;
      settled = true;
      cleanup();
      resolve({
        callId,
        text,
        provider: finalEvent?.provider || null,
        model: finalEvent?.model || model || null,
        usage: usage ? {
          input_tokens: usage.input ?? null,
          output_tokens: usage.output ?? null,
          cache_read_tokens: usage.cacheRead ?? null,
          cache_write_tokens: usage.cacheWrite ?? null,
          reasoning_tokens: usage.reasoning ?? null,
        } : null,
      });
    };
    child.stdout.on("data", onStdout);
    child.stderr.on("data", onStderr);
    child.on("error", onError);
    child.on("close", onClose);
    signal?.addEventListener("abort", abort, { once: true });
    if (signal?.aborted) abort();
  });
}
