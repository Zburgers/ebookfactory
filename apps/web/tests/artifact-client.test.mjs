import test from "node:test";
import assert from "node:assert/strict";

import { fetchProtectedArtifact } from "../src/artifact-client.js";

test("fetchProtectedArtifact sends the owner token to download and preview routes", async () => {
  let request;
  const response = await fetchProtectedArtifact("/projects/project/artifacts/artifact/download", {
    token: "owner-token",
    fetchImpl: async (...args) => {
      request = args;
      return new Response("content", { status: 200 });
    },
  });

  assert.equal(response.status, 200);
  assert.equal(request[0], "/projects/project/artifacts/artifact/download");
  assert.equal(request[1].headers.Authorization, "Bearer owner-token");
});

test("fetchProtectedArtifact does not invent credentials when signed out", async () => {
  let request;
  await fetchProtectedArtifact("/artifact", {
    token: "",
    fetchImpl: async (...args) => {
      request = args;
      return new Response("unauthorized", { status: 401 });
    },
  });

  assert.equal(request[1].headers.Authorization, undefined);
});
