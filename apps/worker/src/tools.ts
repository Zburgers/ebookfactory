/** Scoped tool transport; the API verifies capability scope and expiry. */

export async function invokeScopedTool({ baseUrl, capability, tool, input }) {
  const response = await fetch(`${baseUrl}/private/tools/${encodeURIComponent(tool)}`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "x-tool-capability": capability,
    },
    body: JSON.stringify(input),
  });
  if (!response.ok) throw new Error(`scoped tool failed: ${response.status}`);
  return response.json();
}
