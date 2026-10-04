/**
 * The base URL the SSE streams dial (#1296), resolved like `wsBase` (#944).
 *
 * SSE cannot go through the Next.js rewrite proxy, which buffers chunked
 * responses, so the streams connect to the backend directly. They used to read
 * only `NEXT_PUBLIC_SSE_URL` and otherwise dial a loopback port: a deployment
 * that set just `NEXT_PUBLIC_API_URL`, the documented setup, shipped dead task
 * and stress-test streams. The API origin is the backend, so it is the
 * fallback.
 *
 * Both reads are literal `process.env.NEXT_PUBLIC_*` expressions: Next inlines
 * only that exact textual form into the client bundle (see wsBase.ts).
 */
export interface SseEnvOverrides {
  NEXT_PUBLIC_SSE_URL?: string;
  NEXT_PUBLIC_API_URL?: string;
}

export function sseBase(overrides: SseEnvOverrides = {}): string {
  const explicit = overrides.NEXT_PUBLIC_SSE_URL || process.env.NEXT_PUBLIC_SSE_URL;
  if (explicit) return explicit;
  // prettier-ignore -- one line so the env-var-before-fallback CI check matches.
  return overrides.NEXT_PUBLIC_API_URL || process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8080';
}
