/** Bounded host Pi runner; durable job fencing remains owned by the API. */

import { spawn } from "node:child_process";
import { randomUUID } from "node:crypto";
import { buildPiArgs, parsePiEvent } from "./pi.ts";

export const PRODUCTION_SYSTEM_PROMPT =
  "You are a bounded ebook production worker. Return only useful manuscript text. " +
  "Do not approve work, invoke tools, access files, or change project state.";
export const ORCHESTRATOR_SYSTEM_PROMPT =
  "You are the Ebook Factory main orchestrator and the only agent that speaks to the owner. " +
  "Use the trusted kdp-publish, kdp-audit, and kdp-listing skills as workflow references for Kindle drafting, audit, listing, preparation, and preview guidance. " +
  "Treat their requirements and pricing notes as potentially stale; current official KDP guidance and the application's publishing contract take precedence. " +
  "You have only three trusted project tools: read the current project state, mark a workflow gate, and queue a bounded project-scoped agent. " +
  "Use those tools when needed; never claim that work happened without a tool result or durable context. The tools cannot run arbitrary shell, access host files, or publish externally. " +
  "Never upload to KDP, create or change an Amazon account, enter tax or bank details, buy proof copies, enroll in KDP Select, set pricing, or publish without a separate explicit owner decision; never click publish. " +
  "Return safe plans, bounded decisions, observable status, and owner questions. Do not reveal hidden chain-of-thought, credentials, or private runtime data.";
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
  if (context.task_type === "orchestrator-research") {
    return [
      "You are a bounded research agent working for the Ebook Factory orchestrator.",
      "Return focused evidence and recommendations for the assigned question. Do not write the entire book, invoke tools, access files, reveal secrets, or change project state.",
      "Separate known facts, assumptions, open questions, and a concrete recommendation. Keep the result concise enough for the orchestrator to review.",
      JSON.stringify({ project_id: context.project_id, run_id: context.run_id, instruction: context.instruction, brief: context.brief, context: context.agent_context }),
    ].join("\n\n");
  }
  if (context.task_type === "outline") {
    return [
      "Create a bounded outline for the approved ebook brief.",
      "Return only a concise, non-secret outline with section headings and short descriptions.",
      "Do not invoke tools, access files, or change project state.",
      JSON.stringify({ project_id: context.project_id, run_id: context.run_id, brief: context.brief, budget: context.budget }),
    ].join("\n\n");
  }
  if (context.task_type === "review") {
    return [
      "Perform a bounded editorial review of the persisted manuscript sections.",
      "Return only a concise review report with PASS or NEEDS_REVISION, concrete findings, and actionable corrections.",
      "Do not rewrite the manuscript, invoke tools, access files, or change project state.",
      JSON.stringify({ project_id: context.project_id, run_id: context.run_id, brief: context.brief, review_sections: context.review_sections }),
    ].join("\n\n");
  }
  if (context.task_type === "section-draft") {
    return [
      "Create one bounded section draft for the approved ebook.",
      "Write only the requested section, using its heading and outline input. Do not summarize the entire book or invoke tools.",
      JSON.stringify({ project_id: context.project_id, run_id: context.run_id, section: context.section }),
    ].join("\n\n");
  }
  if (context.task_type === "production" && context.assembly) {
    return [
      "The server will assemble the final manuscript from persisted section revisions.",
      "Do not regenerate prose, invoke tools, or return manuscript content.",
      JSON.stringify({ project_id: context.project_id, run_id: context.run_id, assembly: true }),
    ].join("\n\n");
  }
  const pages = context.brief.target_pages;
  const pageInstruction = pages
    ? `Target ${pages.minimum}-${pages.maximum} pages, using a bounded estimate of 100-180 words per page (${(pages.minimum * 100).toLocaleString()}-${(pages.maximum * 180).toLocaleString()} words). Write an 8-15 sectioned manuscript with one ## heading per section.`
    : "Preserve the requested word target and return a concise title followed by section headings and complete prose.";
  return [
    "Create the next bounded manuscript draft from this approved brief.",
    "Preserve the requested profile, audience, language, length range and output formats.",
    pages ? `Produce a durable sectioned manuscript, not a synopsis or placeholder. ${pageInstruction}` : pageInstruction,
    "Every section must contain complete prose; never emit TODOs, filler, or planning notes as finished text.",
    JSON.stringify({
      project_id: context.project_id,
      run_id: context.run_id,
      brief: context.brief,
      budget: context.budget,
      outline: context.outline,
    }),
  ].join("\n\n");
}

export function runPiProduction({ context, model, thinking = "low", command = "pi", signal, spawnProcess = spawn, onTextDelta, onEvent, skillPaths = [], extensionPaths = [], toolAllowlist = [], noBuiltinTools = false, env, systemPrompt = PRODUCTION_SYSTEM_PROMPT }) {
  const callId = randomUUID();
  const args = buildPiArgs({ prompt: buildProductionPrompt(context), systemPrompt, model, thinking, skillPaths, extensionPaths, toolAllowlist, noBuiltinTools });
  return new Promise((resolve, reject) => {
    const child = spawnProcess(command, args, { stdio: ["ignore", "pipe", "pipe"], shell: false, ...(env ? { env: { ...process.env, ...env } } : {}) });
    const events = [];
    let stdout = "";
    let stderr = "";
    let outputBytes = 0;
    let settled = false;
    let killTimer;
    let deltaQueue = Promise.resolve();
    let deltaError = null;
    let eventQueue = Promise.resolve();
    let eventError = null;
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
    const recordEvent = (line) => {
      const event = parsePiEvent(line);
      if (!event) return;
      events.push(event);
      if (onEvent) {
        eventQueue = eventQueue.then(() => onEvent(event)).catch((error) => {
          eventError ||= error;
        });
      }
      if (event.delta && onTextDelta) {
        deltaQueue = deltaQueue.then(() => onTextDelta(event.delta)).catch((error) => {
          deltaError ||= error;
        });
      }
    };
    const onStdout = (chunk) => {
      if (settled || signal?.aborted) return;
      const textChunk = chunk.toString();
      outputBytes += Buffer.byteLength(textChunk);
      if (outputBytes > MAX_OUTPUT_BYTES) return rejectOutputLimit();
      stdout += textChunk;
      for (const line of stdout.split("\n").slice(0, -1)) {
        recordEvent(line);
      }
      stdout = stdout.split("\n").at(-1) || "";
    };
    const onStderr = (chunk) => { if (!settled) stderr = `${stderr}${chunk}`.slice(-1000); };
    const onError = (error) => settleReject(error);
    const onClose = async (code) => {
      if (settled || signal?.aborted) return settleReject(new Error("Pi production aborted"));
      if (code !== 0) return settleReject(new Error(`Pi production exited with code ${code}: ${stderr.replaceAll(/\s+/g, " ").trim()}`));
      if (stdout.trim()) recordEvent(stdout.trim());
      await deltaQueue;
      if (deltaError) return settleReject(deltaError);
      await eventQueue;
      if (eventError) return settleReject(eventError);
      const finalEvent = [...events].reverse().find((event) => event.type === "message_end" && event.text);
      const completedText = finalEvent?.text || [...events].reverse().find((event) => event.type === "text_end" && event.text)?.text;
      const streamedText = events.map((event) => event.delta).filter(Boolean).join("");
      const text = (completedText || streamedText).trim();
      if (!text) return settleReject(new Error("Pi production returned no manuscript text"));
      if (Buffer.byteLength(text) > MAX_OUTPUT_BYTES) return rejectOutputLimit();
      const usageEvent = [...events].reverse().find((event) => event.usage || event.model || event.provider);
      const usage = usageEvent?.usage;
      settled = true;
      cleanup();
      resolve({
        callId,
        text,
        provider: usageEvent?.provider || null,
        model: usageEvent?.model || model || null,
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
