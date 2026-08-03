/**
 * Both sockets must resolve the same base URL (#944).
 *
 * `AgentTerminal` derived its base from `NEXT_PUBLIC_API_URL` when
 * `NEXT_PUBLIC_WS_URL` was unset; `useAgentChat` hardcoded
 * `ws://localhost:8000`. A deployment setting only `NEXT_PUBLIC_API_URL` — the
 * documented single-origin setup — therefore had a working terminal and a
 * silently dead chat socket, with no error to explain the difference.
 */
import { wsBase } from '@/lib/wsBase';

describe('wsBase (#944)', () => {
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
});
