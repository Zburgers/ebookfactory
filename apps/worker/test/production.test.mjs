import assert from "node:assert/strict";
import { test } from "node:test";
import { buildProductionPrompt } from "../src/production.ts";

test("page-target prompt requests a bounded section plan and derived word budget", () => {
  const prompt = buildProductionPrompt({
    project_id: "p", run_id: "r",
    brief: { target_pages: { minimum: 50, maximum: 150 }, audience: "readers", promise_or_premise: "A durable book" },
    budget: {},
  });
  assert.match(prompt, /8-15 chapters/);
  assert.match(prompt, /6,250-18,000 words/);
  assert.match(prompt, /durable sectioned manuscript/);
});

test("word-target prompt remains compatible", () => {
  const prompt = buildProductionPrompt({
    project_id: "p", run_id: "r", brief: { target_length: { minimum_words: 1000, maximum_words: 2000 } }, budget: {},
  });
  assert.match(prompt, /target_length/);
});
