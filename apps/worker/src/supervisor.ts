/**
 * Small trusted supervisor loop for the private durable-job API.
 *
 * Production execution is deliberately not implemented here yet. The loop
 * owns lease calls and leaves container creation to the next sandbox packet;
 * it never accepts a model-supplied URL, path, or project identity.
 */

const DEFAULT_POLL_MS = 1000;
const DEFAULT_LEASE_SECONDS = 60;

async function apiRequest(baseUrl, token, path, body) {
  const response = await fetch(`${baseUrl}${path}`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "x-ebook-worker-token": token,
    },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`worker API ${response.status}: ${detail.slice(0, 240)}`);
  }
  if (response.status === 204) return null;
  return response.json();
}

/** Claim one job, returning null when the durable queue is empty. */
export function claimOne({ baseUrl, token, workerId, leaseSeconds = DEFAULT_LEASE_SECONDS }) {
  return apiRequest(baseUrl, token, "/private/worker/claim", {
    worker_id: workerId,
    lease_seconds: leaseSeconds,
  });
}

/** Run a cancellable polling loop; task execution is supplied by a trusted callback. */
export async function runSupervisor({
  baseUrl,
  token,
  workerId,
  execute,
  pollMs = DEFAULT_POLL_MS,
  signal,
}) {
  if (!baseUrl || !token || !workerId) throw new Error("baseUrl, token, and workerId are required");
  while (!signal?.aborted) {
    const lease = await claimOne({ baseUrl, token, workerId });
    if (lease) await execute(lease, { baseUrl, token, workerId, signal });
    if (!lease) await new Promise((resolve) => setTimeout(resolve, pollMs));
  }
}
