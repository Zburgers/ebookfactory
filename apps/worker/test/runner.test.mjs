import assert from "node:assert/strict";
import test from "node:test";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

test("outline leases use low-thinking Pi and fenced task-result callback", async () => {
  const { createProductionExecutor } = await import("../src/runner.ts");
  const calls = [];
  const runProduction = async (options) => {
    calls.push(options);
    return { text: "## Opening\nA bounded outline.", callId: "outline-call", usage: { input_tokens: 5, output_tokens: 7 } };
  };
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options });
    if (url.endsWith("/context")) {
      return new Response(JSON.stringify({ task_type: "outline", project_id: "p", run_id: "r", task_id: "t", job_id: "j", brief: {}, budget: {} }), { status: 200 });
    }
    if (url.endsWith("/providers")) return new Response(JSON.stringify([{ provider: "openai-codex", scope: "app", protocol: "pi-native", orchestration_model: "gpt-5.6-luna" }]), { status: 200 });
    if (url.endsWith("/task-result")) return new Response(JSON.stringify({ accepted: true }), { status: 200 });
    throw new Error(`unexpected ${url}`);
  };
  try {
    await createProductionExecutor({ baseUrl: "http://api", token: "secret", workerId: "w", runProduction })({ job_id: "j", generation: 1 });
  } finally {
    globalThis.fetch = originalFetch;
  }
  assert.equal(calls.find((entry) => entry?.thinking !== undefined)?.thinking, "low");
  const taskResult = calls.find((entry) => entry?.url?.endsWith("/task-result"));
  assert.ok(taskResult);
  assert.equal(JSON.parse(taskResult.options.body).result, "## Opening\nA bounded outline.");
});

test("production leases pass bounded outline context and retain production result route", async () => {
  const { createProductionExecutor } = await import("../src/runner.ts");
  const requests = [];
  let received;
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url, options = {}) => {
    requests.push(url);
    if (url.endsWith("/context")) return new Response(JSON.stringify({ task_type: "production", project_id: "p", run_id: "r", task_id: "t", job_id: "j", brief: {}, outline: { result: "outline" }, budget: {} }), { status: 200 });
    if (url.endsWith("/providers")) return new Response(JSON.stringify([{ provider: "openai-codex", scope: "app", protocol: "pi-native", orchestration_model: "gpt-5.6-luna" }]), { status: 200 });
    if (url.endsWith("/production-result")) { received = JSON.parse(options.body); return new Response(JSON.stringify({}), { status: 200 }); }
    throw new Error(`unexpected ${url}`);
  };
  try {
    await createProductionExecutor({ baseUrl: "http://api", token: "secret", workerId: "w", runProduction: async ({ context }) => { assert.equal(context.outline.result, "outline"); return { text: "# book", callId: "production-call" }; }, runArt: async () => null })({ job_id: "j", generation: 1 });
  } finally {
    globalThis.fetch = originalFetch;
  }
  assert.ok(requests.some((url) => url.endsWith("/production-result")));
  assert.equal(received.content, "# book");
});

test("art revision leases call Codex art with owner feedback and use the art result route", async () => {
  const { createProductionExecutor } = await import("../src/runner.ts");
  const dir = await mkdtemp(path.join(tmpdir(), "ebook-art-revision-"));
  const fixture = path.join(dir, "revision.png");
  await writeFile(fixture, Buffer.concat([Buffer.from("\x89PNG\r\n\x1a\n"), Buffer.from("revision")]))
  const calls = [];
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options });
    if (url.endsWith("/context")) return Response.json({
      task_type: "art-revision", project_id: "p", run_id: "r", task_id: "t", job_id: "j", brief: { art_direction: "a blue star" }, budget: {},
      art_revision: { feedback: "Make it anime-inspired and specific.", source_artifact_id: "a" },
    });
    if (url.endsWith("/providers")) return Response.json([{ provider: "openai-codex", scope: "app", protocol: "pi-native", drafting_model: "drafter" }]);
    if (url.endsWith("/art-result")) return Response.json({ accepted: true });
    throw new Error(`unexpected ${url}`);
  };
  let artPrompt;
  try {
    await createProductionExecutor({
      baseUrl: "http://api", token: "secret", workerId: "w",
      runProduction: async () => { throw new Error("Pi must not run for art-only revision"); },
      runArt: async ({ prompt }) => { artPrompt = prompt; return { savedPath: fixture, callId: "art-revision-call", providerRequestId: "resp-art", usage: { input: 2, output: 3 } }; },
    })({ job_id: "j", generation: 1 });
  } finally { globalThis.fetch = originalFetch; await rm(dir, { recursive: true, force: true }); }
  assert.match(artPrompt, /anime-inspired/);
  const callback = calls.find(({ url }) => url.endsWith("/art-result"));
  assert.ok(callback);
  const body = JSON.parse(callback.options.body);
  assert.equal(body.art.call_id, "art-revision-call");
  assert.equal(body.art.filename, "revision.png");
});

test("review leases use low-thinking Pi and fenced task-result accounting", async () => {
  const { createProductionExecutor } = await import("../src/runner.ts");
  const calls = [];
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options });
    if (url.endsWith("/context")) return new Response(JSON.stringify({
      task_type: "review", project_id: "p", run_id: "r", task_id: "t", job_id: "j", brief: {}, budget: {},
      review_sections: [{ section_id: "s1", revision_id: "rev1", heading: "Opening", content: "Persisted prose." }],
    }), { status: 200 });
    if (url.endsWith("/providers")) return new Response(JSON.stringify([{ provider: "openai-codex", scope: "app", protocol: "pi-native", review_model: "gpt-5.6-luna" }]), { status: 200 });
    if (url.endsWith("/task-result")) return new Response(JSON.stringify({ accepted: true }), { status: 200 });
    throw new Error(`unexpected ${url}`);
  };
  try {
    await createProductionExecutor({
      baseUrl: "http://api", token: "secret", workerId: "w",
      runProduction: async (options) => {
        calls.push(options);
        assert.equal(options.thinking, "low");
        assert.equal(options.context.review_sections[0].revision_id, "rev1");
        return { text: "PASS: review complete", callId: "review-call", provider: "openai-codex", model: "gpt-5.6-luna", usage: { input_tokens: 8, output_tokens: 9 } };
      },
    })({ job_id: "j", generation: 1 });
  } finally {
    globalThis.fetch = originalFetch;
  }
  const taskResult = calls.find((entry) => entry?.url?.endsWith("/task-result"));
  assert.ok(taskResult);
  const body = JSON.parse(taskResult.options.body);
  assert.equal(body.result, "PASS: review complete");
  assert.equal(body.call_id, "review-call");
  assert.equal(body.provider, "openai-codex");
  assert.equal(body.model, "gpt-5.6-luna");
});

test("task roles choose their preferred configured models before fallbacks", async () => {
  const { createProductionExecutor } = await import("../src/runner.ts");
  const originalFetch = globalThis.fetch;
  const observed = [];
  globalThis.fetch = async (url) => {
    if (url.endsWith("/context")) return new Response(JSON.stringify({ task_type: globalThis.__taskType, project_id: "p", run_id: "r", task_id: "t", job_id: "j", brief: {}, budget: {} }), { status: 200 });
    if (url.endsWith("/providers")) return new Response(JSON.stringify([{ provider: "openai-codex", scope: "app", protocol: "pi-native", orchestration_model: "orchestrator", drafting_model: "drafter", review_model: "reviewer" }]), { status: 200 });
    return new Response(JSON.stringify({ accepted: true }), { status: 200 });
  };
  try {
    for (const taskType of ["outline", "production", "review"]) {
      globalThis.__taskType = taskType;
      await createProductionExecutor({ baseUrl: "http://api", token: "secret", workerId: "w", runProduction: async ({ model }) => { observed.push(model); return { text: "ok", callId: `${taskType}-call` }; } })({ job_id: "j", generation: 1 });
    }
  } finally {
    delete globalThis.__taskType;
    globalThis.fetch = originalFetch;
  }
  assert.deepEqual(observed, ["orchestrator", "drafter", "reviewer"]);
});

test("section-draft jobs use the task-result route with bounded section context", async () => {
  const originalFetch = globalThis.fetch;
  const received = [];
  globalThis.fetch = async (url, options = {}) => {
    if (url.endsWith("/context")) return new Response(JSON.stringify({ task_type: "section-draft", project_id: "p", run_id: "r", task_id: "t", job_id: "j", brief: {}, budget: {}, section: { heading: "Opening", outline: "Promise." } }), { status: 200 });
    if (url.endsWith("/providers")) return new Response(JSON.stringify([{ provider: "openai-codex", scope: "app", protocol: "pi-native", drafting_model: "drafter" }]), { status: 200 });
    received.push(JSON.parse(options.body));
    return new Response(JSON.stringify({ accepted: true }), { status: 200 });
  };
  try {
    const { createProductionExecutor } = await import("../src/runner.ts");
    await createProductionExecutor({ baseUrl: "http://api", token: "secret", workerId: "w", runProduction: async ({ context }) => { assert.equal(context.section.heading, "Opening"); return { text: "Draft", callId: "section-call", model: "drafter" }; } })({ job_id: "j", generation: 1 });
  } finally { globalThis.fetch = originalFetch; }
  assert.equal(received[0].result, "Draft");
});

test("assembly-ready production jobs call the server assembly route without book content", async () => {
  const originalFetch = globalThis.fetch;
  const requests = [];
  globalThis.fetch = async (url, options = {}) => {
    requests.push({ url, options });
    if (url.endsWith("/context")) return new Response(JSON.stringify({ task_type: "production", assembly: true, project_id: "p", run_id: "r", task_id: "t", job_id: "j", brief: {}, budget: {} }), { status: 200 });
    if (url.endsWith("/providers")) return new Response(JSON.stringify([{ provider: "openai-codex", scope: "app", protocol: "pi-native", drafting_model: "drafter" }]), { status: 200 });
    return new Response(JSON.stringify({ accepted: true }), { status: 200 });
  };
  try {
    const { createProductionExecutor } = await import("../src/runner.ts");
    await createProductionExecutor({ baseUrl: "http://api", token: "secret", workerId: "w", runProduction: async () => { throw new Error("provider must not run for assembly"); } })({ job_id: "j", generation: 1 });
  } finally { globalThis.fetch = originalFetch; }
  const callback = requests.find(({ url }) => url.endsWith("/production-result"));
  assert.ok(callback);
  assert.equal(JSON.parse(callback.options.body).content, "__server_assembly__");
});
