/**
 * Types for the CommonJS security-headers.js (#936).
 *
 * The implementation stays CommonJS because next.config.js `require()`s it and
 * must remain dependency-free; this declaration lets src/proxy.ts import it with
 * ESM syntax, which the lint gate requires.
 */
export interface CspOptions {
  /** Per-request nonce. Required: there is no unsafe-inline fallback (#1305). */
  nonce: string;
}

export function buildCsp(env: NodeJS.ProcessEnv | Record<string, string | undefined>, options: CspOptions): string;
export function buildConnectSrc(sources?: { apiUrl?: string; wsUrl?: string }): string;
export function buildScriptSrc(options: { nonce: string; isDev?: boolean }): string;
export function securityHeaders(): Array<{ key: string; value: string }>;
