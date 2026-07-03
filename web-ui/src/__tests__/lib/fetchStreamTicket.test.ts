/**
 * Tests for `fetchStreamTicket` (issue #745): fetches a short-lived,
 * single-use ticket for SSE/WebSocket stream auth (`?ticket=`), replacing the
 * long-lived JWT previously appended as `?token=`.
 *
 * Isolated in its own file (like verifyAuthAfterStreamFailure.test.ts) so its
 * axios instance mock doesn't collide with api.auth.test.ts, which pokes the
 * real interceptors off the actual axios instance.
 */
const mockInstancePost = jest.fn();

jest.mock('axios', () => {
  const instance = {
    post: (...args: unknown[]) => mockInstancePost(...args),
    interceptors: {
      request: { use: jest.fn() },
      response: { use: jest.fn() },
    },
  };
  return {
    __esModule: true,
    default: {
      create: jest.fn(() => instance),
    },
  };
});

import { fetchStreamTicket } from '@/lib/api';
import { setToken } from '@/lib/auth';

describe('fetchStreamTicket', () => {
  beforeEach(() => {
    mockInstancePost.mockReset();
    localStorage.clear();
  });

  it('returns null WITHOUT calling the endpoint when no token is stored', async () => {
    // Auth-off dev mode has no stored token at all. Calling the endpoint
    // anyway would 401 and trip the response interceptor's redirect-to-login
    // — a guaranteed loop, since the backend would happily stream without a
    // ticket in that mode. Skip the network call entirely.
    await expect(fetchStreamTicket()).resolves.toBeNull();
    expect(mockInstancePost).not.toHaveBeenCalled();
  });

  it('POSTs /auth/stream-ticket and returns the ticket when authenticated', async () => {
    setToken('jwt-abc');
    mockInstancePost.mockResolvedValue({ data: { ticket: 'tk-1', expires_in: 60 } });

    await expect(fetchStreamTicket()).resolves.toBe('tk-1');
    expect(mockInstancePost).toHaveBeenCalledWith('/auth/stream-ticket');
  });

  it('returns null when the request fails (expired token, network error, etc.)', async () => {
    setToken('jwt-abc');
    mockInstancePost.mockRejectedValue(new Error('network error'));

    await expect(fetchStreamTicket()).resolves.toBeNull();
  });
});
