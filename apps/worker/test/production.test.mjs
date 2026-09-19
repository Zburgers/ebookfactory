import assert from "node:assert/strict";
import { test } from "node:test";
import { buildProductionPrompt } from "../src/production.ts";

test("page-target prompt requests the validator-aligned bounded manuscript", () => {
  const prompt = buildProductionPrompt({
    project_id: "p", run_id: "r",
    brief: { target_pages: { minimum: 50, maximum: 150 }, audience: "readers", promise_or_premise: "A durable book" },
    budget: {},
  });
  assert.match(prompt, /100-180 words per page/);
  assert.match(prompt, /5,000-27,000 words/);
  assert.match(prompt, /8-15 sectioned manuscript/);
  assert.doesNotMatch(prompt, /125-120 words per page/);
});

test("word-target prompt remains compatible", () => {
  const prompt = buildProductionPrompt({
    project_id: "p", run_id: "r", brief: { target_length: { minimum_words: 1000, maximum_words: 2000 } }, budget: {},
  });
  assert.match(prompt, /target_length/);
});

test("production prompt carries the durable outline result", () => {
  const prompt = buildProductionPrompt({
    project_id: "p", run_id: "r",
    brief: { target_length: { minimum_words: 1000, maximum_words: 2000 } },
    outline: { task_id: "outline-task", result: "## Opening\nExplain the promise." },
    budget: {},
  });
  assert.match(prompt, /outline-task/);
  assert.match(prompt, /Explain the promise/);
});

test("review prompt consumes bounded persisted section revisions", () => {
  const prompt = buildProductionPrompt({
    project_id: "p", run_id: "r", task_type: "review", brief: { audience: "readers" }, budget: {},
    review_sections: [{ section_id: "s1", revision_id: "rev1", heading: "Opening", content: "A persisted section." }],
  });
  assert.match(prompt, /editorial review/);
  assert.match(prompt, /rev1/);
  assert.match(prompt, /A persisted section/);
});

test("section-draft prompt carries only its bounded outline input", () => {
  const prompt = buildProductionPrompt({ project_id: "p", run_id: "r", task_type: "section-draft", brief: { audience: "readers" }, budget: {}, section: { heading: "Opening", outline: "Establish the promise." } });
  assert.match(prompt, /section draft/);
  assert.match(prompt, /Establish the promise/);
  assert.doesNotMatch(prompt, /review_sections/);
});

test("assembly task asks for server-side persisted section revisions", () => {
  const prompt = buildProductionPrompt({ project_id: "p", run_id: "r", task_type: "production", assembly: true, brief: {}, budget: {} });
  assert.match(prompt, /persisted section revisions/);
  assert.doesNotMatch(prompt, /complete prose/);
});

test("orchestrator research prompt keeps delegated work bounded", () => {
  const prompt = buildProductionPrompt({
    project_id: "p",
    run_id: "r",
    task_type: "orchestrator-research",
    instruction: "Compare ebook preview checks for this brief.",
    agent_context: { source: "owner request" },
    brief: { audience: "readers" },
  });
  assert.match(prompt, /bounded research agent/);
  assert.match(prompt, /Compare ebook preview checks/);
  assert.match(prompt, /known facts, assumptions, open questions/);
  assert.match(prompt, /invoke tools, access files/);
});
