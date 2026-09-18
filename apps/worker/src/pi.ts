/** Explicit Pi CLI resource boundary for the trusted host adapter. */

const RESOURCE_FLAGS = [
  "--no-extensions",
  "--no-skills",
  "--no-prompt-templates",
  "--no-tools",
  "--no-session",
];

export function buildPiArgs({ prompt, systemPrompt, model }) {
  if (!prompt) throw new Error("prompt is required");
  const args = [...RESOURCE_FLAGS];
  if (model) args.push("--model", model);
  if (systemPrompt) args.push("--system-prompt", systemPrompt);
  args.push("-p", prompt);
  return args;
}

export function parsePiEvent(line) {
  try {
    const event = JSON.parse(line);
    return {
      type: event.type,
      provider: event.provider,
      model: event.model,
      usage: event.usage,
      text: event.message?.content ?? event.text,
    };
  } catch {
    return null;
  }
}
