/** Convert an account/rateLimits/read result into redacted persistence rows. */

function asDate(value) {
  if (value === null || value === undefined) return null;
  const date = new Date(typeof value === "number" ? value * 1000 : value);
  return Number.isNaN(date.valueOf()) ? null : date;
}

function limitRows(result) {
  const payload = result?.rateLimits || result?.result?.rateLimits || result?.result || result;
  const limits = payload?.rateLimitsByLimitId || payload?.limits || payload;
  if (!limits || typeof limits !== "object" || Array.isArray(limits)) return [];
  return Object.entries(limits).flatMap(([limitId, value]) => {
    if (!value || typeof value !== "object") return [];
    const window = value.window || value;
    const used = Number(value.usedPercent ?? value.used_percent ?? window.usedPercent ?? window.used_percent);
    const remaining = Number(value.remainingPercent ?? value.remaining_percent ?? window.remainingPercent ?? window.remaining_percent);
    const resetsAt = asDate(value.resetsAt ?? value.resets_at ?? window.resetsAt ?? window.resets_at);
    const windowSeconds = Number(value.windowDurationMins ?? value.window_duration_mins ?? window.windowDurationMins ?? window.window_duration_mins) * 60;
    const supported = Number.isFinite(used) || Number.isFinite(remaining);
    return [{
      provider: "openai-codex",
      account_alias: "subscription",
      bucket: supported && Number.isFinite(windowSeconds) && windowSeconds > 0
        ? `${limitId}-${windowSeconds / 60}m`
        : "unavailable",
      source: "codex app-server account/rateLimits/read",
      observed_at: null,
      stale_after: null,
      used: Number.isFinite(used) ? used : null,
      remaining: Number.isFinite(remaining) ? remaining : (Number.isFinite(used) ? 100 - used : null),
      units: "percent",
      window_seconds: Number.isFinite(windowSeconds) && windowSeconds > 0 ? windowSeconds : null,
      resets_at: resetsAt,
      plan_label: payload.planType || payload.plan_type || null,
      capability_state: supported ? "supported" : "unavailable",
      error: supported ? null : "No percentage window was returned",
    }];
  });
}

export function parseCodexRateLimits(result, observedAt = new Date()) {
  const observed = asDate(observedAt) || new Date();
  const rows = limitRows(result);
  if (!rows.length) {
    return [{
      provider: "openai-codex",
      account_alias: "subscription",
      bucket: "unavailable",
      source: "codex app-server account/rateLimits/read",
      observed_at: observed,
      stale_after: new Date(observed.valueOf() + 5 * 60 * 1000),
      used: null,
      remaining: null,
      units: "percent",
      window_seconds: null,
      resets_at: null,
      plan_label: null,
      capability_state: "unavailable",
      error: "No rate-limit windows were returned",
    }];
  }
  return rows.map((row) => ({
    ...row,
    observed_at: observed,
    stale_after: new Date(observed.valueOf() + Math.max(row.window_seconds || 300, 300) * 1000),
  }));
}
