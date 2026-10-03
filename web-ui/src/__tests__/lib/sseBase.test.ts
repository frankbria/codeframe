/**
 * The SSE streams must find the backend the way the sockets do (#1296).
 *
 * `useTaskStream` and `useStressTestStream` read only `NEXT_PUBLIC_SSE_URL`
 * and otherwise dialled `http://localhost:8000` — the #944 WebSocket bug in
 * its SSE form. Nothing in the documented setup sets that variable, so a
 * self-hoster shipped dead task and stress-test streams.
 */
import fs from 'fs';
import path from 'path';

import { sseBase } from '@/lib/sseBase';

const ENV_KEYS = ['NEXT_PUBLIC_SSE_URL', 'NEXT_PUBLIC_API_URL'] as const;

describe('sseBase (#1296)', () => {
  const saved: Record<string, string | undefined> = {};

  beforeEach(() => {
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

  it('uses NEXT_PUBLIC_API_URL when no SSE URL is set', () => {
    expect(sseBase({ NEXT_PUBLIC_API_URL: 'https://app.example.com' })).toBe(
      'https://app.example.com'
    );
  });

  it('prefers an explicit NEXT_PUBLIC_SSE_URL', () => {
    expect(
      sseBase({
        NEXT_PUBLIC_API_URL: 'https://app.example.com',
        NEXT_PUBLIC_SSE_URL: 'https://events.example.com',
      })
    ).toBe('https://events.example.com');
  });

  it('falls back to the local backend on cf serve’s default port', () => {
    expect(sseBase({})).toBe('http://localhost:8080');
  });

  it('picks up the ambient variables with no override supplied', () => {
    process.env.NEXT_PUBLIC_API_URL = 'https://ambient.example.com';
    expect(sseBase()).toBe('https://ambient.example.com');
  });

  describe('reads the environment the way Next can actually inline', () => {
    const source = fs.readFileSync(path.join(process.cwd(), 'src/lib/sseBase.ts'), 'utf8');

    it.each(ENV_KEYS)('reads %s as a literal process.env expression', (key) => {
      expect(source).toContain(`process.env.${key}`);
    });

    it('does not read the env through an indirect reference', () => {
      expect(source).not.toMatch(/=\s*process\.env\b(?!\.)/);
    });
  });

  it.each(['src/hooks/useTaskStream.ts', 'src/hooks/useStressTestStream.ts'])(
    '%s resolves its base through sseBase, with no localhost of its own',
    (file) => {
      const source = fs.readFileSync(path.join(process.cwd(), file), 'utf8');
      expect(source).toMatch(/import \{ sseBase \} from '@\/lib\/sseBase'/);
      expect(source).not.toMatch(/localhost/);
    }
  );
});
