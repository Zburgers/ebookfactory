/**
 * Small trusted supervisor loop for the private durable-job API.
 *
 * Production execution is supplied by a trusted callback. The loop
 * owns lease calls and leaves container/model-gateway lifecycle to the
 * supervisor integration packet;
 * it never accepts a model-supplied URL, path, or project identity.
 */

const DEFAULT_POLL_MS = 1000;
const DEFAULT_LEASE_SECONDS = 60;
const DEFAULT_RETRY_DELAY_MS = 1000;
const MAX_BACKOFF_MS = 30_000;
const MAX_MUTATION_ATTEMPTS = 3;
const MAX_HEARTBEAT_FAILURES = 3;
const DEFAULT_REQUEST_TIMEOUT_MS = 10_000;
const MAX_RESPONSE_BYTES = 64 * 1024;
const EXECUTION_ERROR_CLASS = "worker_execution_failure";

async function apiRequest(baseUrl, token, path, body, signal, requestTimeoutMs = DEFAULT_REQUEST_TIMEOUT_MS) {
  const requestController = new AbortController();
  const abortRequest = () => requestController.abort();
  const timeout = setTimeout(() => requestController.abort(), requestTimeoutMs);
  signal?.addEventListener("abort", abortRequest, { once: true });
  if (signal?.aborted) abortRequest();
  try {
    const response = await fetch(`${baseUrl}${path}`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "x-ebook-worker-token": token,
    },
    body: JSON.stringify(body),
      signal: requestController.signal,
    });
    const detail = await readBoundedResponse(response);
    if (!response.ok) {
      const error = new Error(`worker API ${response.status}: ${detail.slice(0, 240)}`);
      error.status = response.status;
      throw error;
    }
    if (response.status === 204 || !detail) return null;
    try { return JSON.parse(detail); } catch { throw new Error("worker API returned malformed JSON"); }
  } finally {
    clearTimeout(timeout);
    signal?.removeEventListener("abort", abortRequest);
  }
}

async function readBoundedResponse(response) {
  const reader = response.body?.getReader();
  if (!reader) return "";
  const chunks = [];
  let size = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > MAX_RESPONSE_BYTES) {
        await reader.cancel();
        throw new Error("worker API response exceeded limit");
      }
      chunks.push(value);
    }
  } finally {
    reader.releaseLock();
  }
  return new TextDecoder().decode(Buffer.concat(chunks.map((chunk) => Buffer.from(chunk))));
}

/** Claim one job, returning null when the durable queue is empty. */
export function claimOne({ baseUrl, token, workerId, leaseSeconds = DEFAULT_LEASE_SECONDS, signal }) {
  return apiRequest(baseUrl, token, "/private/worker/claim", {
    worker_id: workerId,
    lease_seconds: leaseSeconds,
  }, signal);
}

/** Run a cancellable polling loop; task execution is supplied by a trusted callback. */
export async function runSupervisor({
  baseUrl,
  token,
  workerId,
  execute,
  pollMs = DEFAULT_POLL_MS,
  leaseSeconds = DEFAULT_LEASE_SECONDS,
  heartbeatMs = Math.max(1000, Math.floor((leaseSeconds * 1000) / 3)),
  retryDelayMs = DEFAULT_RETRY_DELAY_MS,
  requestTimeoutMs = DEFAULT_REQUEST_TIMEOUT_MS,
  signal,
}) {
  if (!baseUrl || !token || !workerId) throw new Error("baseUrl, token, and workerId are required");
  let failureBackoffMs = retryDelayMs;
  while (!signal?.aborted) {
    let lease;
    try {
      lease = await claimOne({ baseUrl, token, workerId, leaseSeconds, signal });
      failureBackoffMs = retryDelayMs;
    } catch {
      await sleep(failureBackoffMs, signal);
      failureBackoffMs = Math.min(MAX_BACKOFF_MS, Math.max(retryDelayMs, failureBackoffMs * 2));
      continue;
    }
    if (!lease) {
      await sleep(pollMs, signal);
      continue;
    }

    try {
      await runLease({
        baseUrl,
        token,
        workerId,
        lease,
        leaseSeconds,
        execute,
        heartbeatMs,
        retryDelayMs,
        requestTimeoutMs,
        signal,
      });
    } catch {
      await sleep(retryDelayMs, signal);
    }
  }
}

function sleep(milliseconds, signal) {
  if (signal?.aborted) return Promise.resolve();
  return new Promise((resolve) => {
    let timer;
    const onAbort = () => {
      clearTimeout(timer);
      signal?.removeEventListener("abort", onAbort);
      resolve();
    };
    timer = setTimeout(onAbort, milliseconds);
    signal?.addEventListener("abort", onAbort, { once: true });
  });
}

async function runLease({
  baseUrl,
  token,
  workerId,
  lease,
  leaseSeconds,
  execute,
  heartbeatMs,
  retryDelayMs,
  requestTimeoutMs,
  signal,
}) {
  const executionController = new AbortController();
  const abortExecution = () => executionController.abort();
  signal?.addEventListener("abort", abortExecution, { once: true });
  if (signal?.aborted) abortExecution();
  const identity = {
    job_id: lease.job_id,
    worker_id: workerId,
    generation: lease.generation,
    lease_seconds: lease.lease_seconds ?? leaseSeconds,
  };
  let heartbeatInFlight = false;
  let heartbeatFailures = 0;
  let leaseLost = false;
  const heartbeat = async () => {
    if (executionController.signal.aborted || heartbeatInFlight || leaseLost) return;
    heartbeatInFlight = true;
    try {
      await apiRequest(baseUrl, token, "/private/worker/heartbeat", identity, executionController.signal, requestTimeoutMs);
      heartbeatFailures = 0;
    } catch (error) {
      if (executionController.signal.aborted) return;
      if (error.status === 409) {
        leaseLost = true;
        executionController.abort();
      } else {
        heartbeatFailures += 1;
        if (heartbeatFailures >= MAX_HEARTBEAT_FAILURES) {
          leaseLost = true;
          executionController.abort();
        }
      }
    } finally {
      heartbeatInFlight = false;
    }
  };
  const heartbeatTimer = setInterval(heartbeat, heartbeatMs);
  try {
    let resultRefs;
    try {
      if (executionController.signal.aborted) return;
      const result = await executeWithAbort(
        execute(lease, { baseUrl, token, workerId, signal: executionController.signal }),
        executionController.signal,
      );
      if (result?.terminal === true) return;
      resultRefs = normalizeResultRefs(result);
    } catch {
      if (!leaseLost && !signal?.aborted) await failLease(baseUrl, token, identity, retryDelayMs, signal, requestTimeoutMs);
      return;
    }
    if (leaseLost) return;
    if (signal?.aborted) return;
    try {
      await mutationWithRetry(baseUrl, token, "/private/worker/complete", {
        job_id: identity.job_id,
        worker_id: identity.worker_id,
        generation: identity.generation,
        result_refs: resultRefs,
      }, retryDelayMs, executionController.signal, requestTimeoutMs);
    } catch {
      return;
    }
  } finally {
    clearInterval(heartbeatTimer);
    signal?.removeEventListener("abort", abortExecution);
  }
}

function executeWithAbort(promise, signal) {
  if (signal?.aborted) return Promise.reject(new Error("worker execution aborted"));
  if (!signal) return promise;
  let abortExecution;
  const aborted = new Promise((_, reject) => {
    abortExecution = () => reject(new Error("worker execution aborted"));
    signal.addEventListener("abort", abortExecution, { once: true });
  });
  return Promise.race([promise, aborted]).finally(() => signal.removeEventListener("abort", abortExecution));
}

function normalizeResultRefs(result) {
  if (result === undefined || result === null) return {};
  if (typeof result !== "object" || Array.isArray(result)) {
    throw new Error("worker result_refs must be an object");
  }
  return result;
}

async function failLease(baseUrl, token, identity, retryDelayMs, signal, requestTimeoutMs) {
  try {
    await mutationWithRetry(baseUrl, token, "/private/worker/fail", {
      job_id: identity.job_id,
      worker_id: identity.worker_id,
      generation: identity.generation,
      error_class: EXECUTION_ERROR_CLASS,
      retryable: true,
      retry_after_seconds: Math.max(0, retryDelayMs / 1000),
    }, retryDelayMs, signal, requestTimeoutMs);
  } catch {
    // A failed report leaves the lease for durable expiry/reclaim; never stop
    // the polling supervisor because the callback transport is unavailable.
  }
}

async function mutationWithRetry(baseUrl, token, path, body, retryDelayMs, signal, requestTimeoutMs) {
  for (let attempt = 1; attempt <= MAX_MUTATION_ATTEMPTS; attempt += 1) {
    if (signal?.aborted) return false;
    try {
      await apiRequest(baseUrl, token, path, body, signal, requestTimeoutMs);
      return true;
    } catch (error) {
      if (error.status === 409) return false;
      if (signal?.aborted) return false;
      const transient = error.status === undefined || error.status >= 500;
      if (!transient || attempt === MAX_MUTATION_ATTEMPTS) throw error;
      const delay = Math.min(MAX_BACKOFF_MS, Math.max(0, retryDelayMs) * 2 ** (attempt - 1));
      await sleep(delay, signal);
      if (signal?.aborted) return false;
    }
  }
  return false;
}
