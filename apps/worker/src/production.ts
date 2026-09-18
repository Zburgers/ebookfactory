/** Bounded host Pi runner; durable job fencing remains owned by the API. */

import { spawn } from "node:child_process";
import { randomUUID } from "node:crypto";
import { buildPiArgs, parsePiEvent } from "./pi.ts";

const SYSTEM_PROMPT =
  "You are a bounded ebook production worker. Return only useful manuscript text. " +
  "Do not approve work, invoke tools, access files, or change project state.";

export function buildProductionPrompt(context) {
  if (!context?.project_id || !context?.run_id || !context?.brief) throw new Error("incomplete production context");
  return [
    "Create the next bounded manuscript draft from this approved brief.",
    "Preserve the requested profile, audience, language, length range and output formats.",
    "Return a concise title followed by section headings and complete prose.",
    JSON.stringify({ project_id: context.project_id, run_id: context.run_id, brief: context.brief, budget: context.budget }),
  ].join("\n\n");
}

export function runPiProduction({ context, model, command = "pi" }) {
  const callId = randomUUID();
  const args = buildPiArgs({ prompt: buildProductionPrompt(context), systemPrompt: SYSTEM_PROMPT, model, thinking: "low" });
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { stdio: ["ignore", "pipe", "pipe"], shell: false });
    const events = [];
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => {
      stdout += chunk.toString();
      for (const line of stdout.split("\n").slice(0, -1)) {
        const event = parsePiEvent(line);
        if (event) events.push(event);
      }
      stdout = stdout.split("\n").at(-1) || "";
    });
    child.stderr.on("data", (chunk) => { stderr = `${stderr}${chunk}`.slice(-1000); });
    child.on("error", reject);
    child.on("close", (code) => {
      if (code !== 0) return reject(new Error(`Pi production exited with code ${code}: ${stderr.replaceAll(/\s+/g, " ").trim()}`));
      const text = events.map((event) => event.text).filter(Boolean).join("\n").trim();
      if (!text) return reject(new Error("Pi production returned no manuscript text"));
      const finalEvent = [...events].reverse().find((event) => event.usage || event.model || event.provider);
      const usage = finalEvent?.usage;
      resolve({
        callId,
        text,
        provider: finalEvent?.provider || null,
        model: finalEvent?.model || model || null,
        usage: usage
          ? {
              input_tokens: usage.input ?? null,
              output_tokens: usage.output ?? null,
              cache_read_tokens: usage.cacheRead ?? null,
              cache_write_tokens: usage.cacheWrite ?? null,
              reasoning_tokens: usage.reasoning ?? null,
            }
          : null,
      });
    });
  });
}
