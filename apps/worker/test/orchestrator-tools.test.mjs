import assert from "node:assert/strict";
import test from "node:test";
import registerOrchestratorTools from "../src/orchestrator-tools.mjs";

test("orchestrator extension exposes only the bounded project tool surface", () => {
  const tools = [];
  registerOrchestratorTools({ registerTool: (tool) => tools.push(tool) });

  assert.deepEqual(tools.map((tool) => tool.name), [
    "factory_read_state",
    "factory_mark_gate",
    "factory_spawn_agent",
  ]);
  assert.equal(tools.some((tool) => tool.name === "bash"), false);
  assert.equal(tools.find((tool) => tool.name === "factory_spawn_agent").parameters.properties.role.enum.includes("research"), true);
  const gate = tools.find((tool) => tool.name === "factory_mark_gate");
  assert.deepEqual(gate.parameters.properties.evidence, {
    type: "array",
    items: { type: "string" },
    maxItems: 20,
    description: "Bounded evidence references, such as artifacts or events",
  });
});
