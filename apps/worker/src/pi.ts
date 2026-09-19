/** Explicit Pi CLI resource boundary for the trusted host adapter. */

const RESOURCE_FLAGS = [
  "--no-extensions",
  "--no-skills",
  "--no-prompt-templates",
  "--no-tools",
  "--no-session",
];

export function buildPiArgs({
  prompt,
  systemPrompt,
  model,
  thinking = "low",
  skillPaths = [],
  extensionPaths = [],
  toolAllowlist = [],
  noBuiltinTools = false,
}) {
  if (!prompt) throw new Error("prompt is required");
  const args = noBuiltinTools ? RESOURCE_FLAGS.filter((flag) => flag !== "--no-tools") : [...RESOURCE_FLAGS];
  for (const skillPath of skillPaths) {
    if (typeof skillPath !== "string" || !skillPath.trim()) throw new Error("skill paths must be non-empty strings");
    args.push("--skill", skillPath);
  }
  for (const extensionPath of extensionPaths) {
    if (typeof extensionPath !== "string" || !extensionPath.trim()) throw new Error("extension paths must be non-empty strings");
    args.push("--extension", extensionPath);
  }
  args.push("--mode", "json");
  if (noBuiltinTools) args.push("--no-builtin-tools");
  if (toolAllowlist.length) {
    if (!toolAllowlist.every((tool) => typeof tool === "string" && tool.trim())) throw new Error("tool names must be non-empty strings");
    args.push("--tools", toolAllowlist.join(","));
  }
  args.push("--thinking", thinking, "--print");
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
    const parsed = {
      type: event.type,
      provider: event.provider ?? message?.provider,
      model: event.model ?? message?.model,
      usage: event.usage ?? message?.usage,
      delta: event.type === "message_update" && assistantMessageEvent?.type === "text_delta" ? assistantMessageEvent.delta : "",
      text: isFinalAssistantMessage || event.type === "text_end" ? piContentToText(content) : "",
    };
    if (event.type.startsWith("tool_execution_")) {
      parsed.toolCallId = event.toolCallId ?? event.id ?? undefined;
      parsed.toolName = event.toolName ?? undefined;
      parsed.args = event.args ?? event.arguments ?? undefined;
      parsed.result = event.result ?? undefined;
      parsed.isError = event.isError ?? undefined;
    }
    return parsed;
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
