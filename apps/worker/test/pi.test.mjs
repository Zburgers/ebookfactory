import assert from "node:assert/strict";
import { EventEmitter } from "node:events";
import { test } from "node:test";
import { buildPiArgs, parsePiEvent } from "../src/pi.ts";
import { runPiProduction } from "../src/production.ts";

test("buildPiArgs keeps discovery disabled while explicitly loading trusted skills", () => {
  const args = buildPiArgs({
    prompt: "hello",
    systemPrompt: "system",
    model: "test-model",
    skillPaths: ["/home/naki/.codex/skills/kdp-publish"],
  });

  assert.equal(args.includes("--no-skills"), true);
  assert.deepEqual(args.slice(args.indexOf("--skill"), args.indexOf("--mode")), [
    "--skill",
    "/home/naki/.codex/skills/kdp-publish",
  ]);
});

test("buildPiArgs can enable only the trusted project extension tools", () => {
  const args = buildPiArgs({
    prompt: "hello",
    systemPrompt: "system",
    model: "test-model",
    skillPaths: ["/trusted/kdp-publish"],
    extensionPaths: ["/trusted/orchestrator-tools.mjs"],
    toolAllowlist: ["factory_read_state", "factory_mark_gate"],
    noBuiltinTools: true,
  });

  assert.equal(args.includes("--no-builtin-tools"), true);
  assert.equal(args.includes("--no-tools"), false);
  assert.deepEqual(args.slice(args.indexOf("--extension"), args.indexOf("--mode")), [
    "--extension",
    "/trusted/orchestrator-tools.mjs",
  ]);
  assert.deepEqual(args.slice(args.indexOf("--tools"), args.indexOf("--thinking")), [
    "--tools",
    "factory_read_state,factory_mark_gate",
  ]);
});

test("parsePiEvent exposes Pi JSON text deltas without treating them as final output", () => {
  const parsed = parsePiEvent(JSON.stringify({
    type: "message_update",
    usage: { input: 4, output: 1 },
    assistantMessageEvent: { type: "text_delta", contentIndex: 0, delta: "Hello " },
  }));

  assert.deepEqual(parsed, {
    type: "message_update",
    provider: undefined,
    model: undefined,
    usage: { input: 4, output: 1 },
    delta: "Hello ",
    text: "",
  });
});

test("parsePiEvent exposes tool execution lifecycle data", () => {
  assert.deepEqual(parsePiEvent(JSON.stringify({
    type: "tool_execution_start",
    toolCallId: "call-1",
    toolName: "factory_read_state",
    args: { focus: "gates" },
  })), {
    type: "tool_execution_start",
    provider: undefined,
    model: undefined,
    usage: undefined,
    delta: "",
    text: "",
    toolCallId: "call-1",
    toolName: "factory_read_state",
    args: { focus: "gates" },
    result: undefined,
    isError: undefined,
  });
});

test("runPiProduction forwards deltas and uses the authoritative final message once", async () => {
  const deltas = [];
  const spawnProcess = () => {
    const child = new EventEmitter();
    child.stdout = new EventEmitter();
    child.stderr = new EventEmitter();
    child.kill = () => {};
    queueMicrotask(() => {
      child.stdout.emit("data", Buffer.from([
        JSON.stringify({ type: "message_update", assistantMessageEvent: { type: "text_delta", delta: "Hello " } }),
        JSON.stringify({ type: "message_update", assistantMessageEvent: { type: "text_delta", delta: "world" } }),
        JSON.stringify({ type: "message_end", message: { role: "assistant", content: [{ type: "text", text: "Hello world" }] } }),
      ].join("\n") + "\n"));
      child.emit("close", 0);
    });
    return child;
  };

  const result = await runPiProduction({
    context: { project_id: "p", messages: [{ role: "user", content: "hi" }] },
    model: "test-model",
    spawnProcess,
    onTextDelta: async (delta) => deltas.push(delta),
  });

  assert.equal(result.text, "Hello world");
  assert.deepEqual(deltas, ["Hello ", "world"]);
});

test("runPiProduction forwards structured tool activity to the durable caller", async () => {
  const activities = [];
  const spawnProcess = () => {
    const child = new EventEmitter();
    child.stdout = new EventEmitter();
    child.stderr = new EventEmitter();
    child.kill = () => {};
    queueMicrotask(() => {
      child.stdout.emit("data", Buffer.from([
        JSON.stringify({ type: "tool_execution_start", toolCallId: "call-1", toolName: "factory_read_state", args: { focus: "gates" } }),
        JSON.stringify({ type: "tool_execution_end", toolCallId: "call-1", toolName: "factory_read_state", result: { content: [{ type: "text", text: "state" }] }, isError: false }),
        JSON.stringify({ type: "message_end", message: { role: "assistant", content: [{ type: "text", text: "Done" }] } }),
      ].join("\n") + "\n"));
      child.emit("close", 0);
    });
    return child;
  };

  await runPiProduction({
    context: { project_id: "p", messages: [{ role: "user", content: "hi" }] },
    model: "test-model",
    spawnProcess,
    onEvent: async (event) => activities.push(event),
  });

  assert.deepEqual(activities.map((event) => event.type), ["tool_execution_start", "tool_execution_end", "message_end"]);
  assert.equal(activities[0].toolName, "factory_read_state");
});

test("runPiProduction forwards explicit skill paths without enabling discovery", async () => {
  let observedArgs;
  const spawnProcess = (_command, args) => {
    observedArgs = args;
    const child = new EventEmitter();
    child.stdout = new EventEmitter();
    child.stderr = new EventEmitter();
    child.kill = () => {};
    queueMicrotask(() => {
      child.stdout.emit("data", Buffer.from(JSON.stringify({ type: "message_end", message: { role: "assistant", content: "final" } })));
      child.emit("close", 0);
    });
    return child;
  };

  await runPiProduction({
    context: { project_id: "p", messages: [] },
    model: "test-model",
    skillPaths: ["/trusted/kdp-publish"],
    spawnProcess,
  });

  assert.equal(observedArgs.includes("--no-skills"), true);
  assert.deepEqual(observedArgs.slice(observedArgs.indexOf("--skill"), observedArgs.indexOf("--mode")), [
    "--skill",
    "/trusted/kdp-publish",
  ]);
});

test("runPiProduction flushes a final JSON event without a trailing newline", async () => {
  const spawnProcess = () => {
    const child = new EventEmitter();
    child.stdout = new EventEmitter();
    child.stderr = new EventEmitter();
    child.kill = () => {};
    queueMicrotask(() => {
      child.stdout.emit("data", Buffer.from(JSON.stringify({ type: "message_end", message: { role: "assistant", content: "final record" } })));
      child.emit("close", 0);
    });
    return child;
  };
  const result = await runPiProduction({ context: { project_id: "p", messages: [] }, model: "test-model", spawnProcess });
  assert.equal(result.text, "final record");
});
