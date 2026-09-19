/** Explicit Pi CLI resource boundary for the trusted host adapter. */

const RESOURCE_FLAGS = [
  "--no-extensions",
  "--no-skills",
  "--no-prompt-templates",
  "--no-tools",
  "--no-session",
];

export function buildPiArgs({ prompt, systemPrompt, model, thinking = "low" }) {
  if (!prompt) throw new Error("prompt is required");
  const args = [...RESOURCE_FLAGS];
  args.push("--mode", "json", "--print", "--thinking", thinking);
  if (model) args.push("--model", model);
  if (systemPrompt) args.push("--system-prompt", systemPrompt);
  args.push("-p", prompt);
  return args;
}

export function parsePiEvent(line) {
  try {
    const event = JSON.parse(line);
    const message = event.message;
    const assistantMessageEvent = event.assistantMessageEvent;
    const isFinalAssistantMessage = event.type === "message_end" && message?.role === "assistant";
    const content = isFinalAssistantMessage ? message.content : event.type === "text_end" ? event.content : event.text;
    return {
      type: event.type,
      provider: event.provider ?? message?.provider,
      model: event.model ?? message?.model,
      usage: event.usage ?? message?.usage,
      delta: event.type === "message_update" && assistantMessageEvent?.type === "text_delta" ? assistantMessageEvent.delta : "",
      text: isFinalAssistantMessage || event.type === "text_end" ? piContentToText(content) : "",
    };
  } catch {
    return null;
  }
}

function piContentToText(content) {
  if (typeof content === "string") return content;
  if (!Array.isArray(content)) return content == null ? "" : String(content);
  return content
    .map((part) => {
      if (typeof part === "string") return part;
      if (part && typeof part.text === "string") return part.text;
      if (part && typeof part.content === "string") return part.content;
      return "";
    })
    .join("");
}
