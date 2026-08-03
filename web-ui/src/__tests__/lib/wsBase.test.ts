/**
 * Both sockets must resolve the same base URL (#944).
 *
 * `AgentTerminal` derived its base from `NEXT_PUBLIC_API_URL` when
 * `NEXT_PUBLIC_WS_URL` was unset; `useAgentChat` hardcoded
 * `ws://localhost:8000`. A deployment setting only `NEXT_PUBLIC_API_URL` — the
 * documented single-origin setup — therefore had a working terminal and a
 * silently dead chat socket, with no error to explain the difference.
 */
import fs from 'fs';
import path from 'path';

import { wsBase } from '@/lib/wsBase';

describe('wsBase (#944)', () => {
  const ENV_KEYS = ['NEXT_PUBLIC_WS_URL', 'NEXT_PUBLIC_API_URL'] as const;
  const saved: Record<string, string | undefined> = {};

  beforeEach(() => {
    // The overrides are meant to be read INSTEAD of the ambient environment;
    // a CI runner that exports either variable must not change any assertion.
    ENV_KEYS.forEach((k) => {
      saved[k] = process.env[k];
      delete process.env[k];
    });
  });

  afterEach(() => {
    ENV_KEYS.forEach((k) => {
      if (saved[k] === undefined) delete process.env[k];
      else process.env[k] = saved[k];
    });
  });

  it('derives the ws base from NEXT_PUBLIC_API_URL alone', () => {
    // The AC's exact scenario: one variable set, both sockets must agree.
    expect(wsBase({ NEXT_PUBLIC_API_URL: 'http://api.example.com' })).toBe(
      'ws://api.example.com'
    );
  });

  it('upgrades https to wss, never downgrading a TLS deployment', () => {
    expect(wsBase({ NEXT_PUBLIC_API_URL: 'https://app.example.com' })).toBe(
      'wss://app.example.com'
    );
  });

  it('prefers an explicit NEXT_PUBLIC_WS_URL', () => {
    expect(
      wsBase({
        NEXT_PUBLIC_API_URL: 'https://app.example.com',
        NEXT_PUBLIC_WS_URL: 'wss://sockets.example.com',
      })
    ).toBe('wss://sockets.example.com');
  });

  it('falls back to localhost when nothing is configured', () => {
    expect(wsBase({})).toBe('ws://localhost:8000');
  });

  it('never returns the old hardcoded value when an API URL is set', () => {
    // The chat hook's old constant. If this ever comes back, the chat socket
    // is dead on every real deployment.
    expect(wsBase({ NEXT_PUBLIC_API_URL: 'https://app.example.com' })).not.toBe(
      'ws://localhost:8000'
    );
  });

  describe('reads the environment the way Next can actually inline', () => {
    // The first cut took `env: Record<string, string|undefined> = process.env`
    // and read `env.NEXT_PUBLIC_API_URL`. That looks equivalent and is not:
    // Next's build-time substitution is TEXTUAL on `process.env.NEXT_PUBLIC_X`,
    // so an indirect read compiles to a lookup on the client's empty
    // `process.env` stub — undefined, always the localhost fallback. Both
    // callers are client components, so it would have shipped broken.
    const source = fs.readFileSync(
      path.join(process.cwd(), 'src/lib/wsBase.ts'),
      'utf8'
    );

    it.each(ENV_KEYS)('reads %s as a literal process.env expression', (key) => {
      expect(source).toContain(`process.env.${key}`);
    });

    it('does not read the env through an indirect reference', () => {
      expect(source).not.toMatch(/=\s*process\.env\b(?!\.)/);
    });

    it('picks up the ambient variable with no override supplied', () => {
      process.env.NEXT_PUBLIC_API_URL = 'https://ambient.example.com';

      expect(wsBase()).toBe('wss://ambient.example.com');
    });

    it('lets an override win over the ambient variable', () => {
      process.env.NEXT_PUBLIC_API_URL = 'https://ambient.example.com';

      expect(wsBase({ NEXT_PUBLIC_API_URL: 'http://explicit.example.com' })).toBe(
        'ws://explicit.example.com'
      );
    });
  });
});
