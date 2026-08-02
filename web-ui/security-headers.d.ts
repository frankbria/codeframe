/**
 * Types for the CommonJS security-headers.js (#936).
 *
 * The implementation stays CommonJS because next.config.js `require()`s it and
 * must remain dependency-free; this declaration lets src/proxy.ts import it with
 * ESM syntax, which the lint gate requires.
 */
export interface CspOptions {
  /** Per-request nonce. Omit for the non-document fallback policy. */
  nonce?: string;
}

export function buildCsp(env?: NodeJS.ProcessEnv, options?: CspOptions): string;
export function buildConnectSrc(sources?: { apiUrl?: string; wsUrl?: string }): string;
export function buildScriptSrc(options?: { nonce?: string; isDev?: boolean }): string;
export function securityHeaders(): Array<{ key: string; value: string }>;
