/**
 * Host-side gateway seam. It accepts only an explicit configured endpoint;
 * production containers will receive a short-lived scoped URL in P04.
 */

export function configuredGatewayUrl(endpoint) {
  if (!endpoint) throw new Error("model gateway endpoint is not configured");
  const url = new URL(endpoint);
  if (!['http:', 'https:'].includes(url.protocol)) throw new Error("unsupported gateway protocol");
  return url.toString();
}
