/** Provider API client; credential bytes are never accepted by this module. */

export async function listProviders({ baseUrl }) {
  const response = await fetch(`${baseUrl}/providers`);
  if (!response.ok) throw new Error(`provider list failed: ${response.status}`);
  return response.json();
}

export async function saveProviderMetadata({ baseUrl, provider, settings }) {
  const response = await fetch(`${baseUrl}/providers/${encodeURIComponent(provider)}`, {
    method: "PUT",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(settings),
  });
  if (!response.ok) throw new Error(`provider save failed: ${response.status}`);
  return response.json();
}
