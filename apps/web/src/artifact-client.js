export function fetchProtectedArtifact(path, { token = "", fetchImpl = globalThis.fetch, ...options } = {}) {
  const headers = { ...(options.headers || {}) };
  if (token) headers.Authorization = `Bearer ${token}`;
  return fetchImpl(path, { ...options, headers });
}
