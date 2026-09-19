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
