/**
 * Tests for the SSE/WS re-auth probe (#651). Mocks axios so we can control the
 * shared client's `get('/users/me')` outcome without a real server. Isolated in
 * its own file so the axios mock does not affect api.auth.test.ts (which pokes
 * the real interceptors).
 */
const mockGet = jest.fn();

jest.mock('axios', () => {
  const instance = {
    get: (...args: unknown[]) => mockGet(...args),
    interceptors: {
      request: { use: jest.fn() },
      response: { use: jest.fn() },
    },
  };
  return {
    __esModule: true,
    default: {
      create: jest.fn(() => instance),
      isAxiosError: jest.fn(() => false),
    },
    isAxiosError: jest.fn(() => false),
  };
});

import { verifyAuthAfterStreamFailure } from '@/lib/api';

describe('verifyAuthAfterStreamFailure', () => {
  beforeEach(() => {
    mockGet.mockReset();
  });

  it('probes the lightweight /users/me endpoint', async () => {
    mockGet.mockResolvedValue({ data: { id: '1' } });
    await verifyAuthAfterStreamFailure();
    expect(mockGet).toHaveBeenCalledWith('/users/me');
  });

  it('resolves (never throws) when the probe succeeds', async () => {
    mockGet.mockResolvedValue({ data: {} });
    await expect(verifyAuthAfterStreamFailure()).resolves.toBeUndefined();
  });

  it('swallows probe errors so callers can fire-and-forget', async () => {
    mockGet.mockRejectedValue(new Error('401'));
    await expect(verifyAuthAfterStreamFailure()).resolves.toBeUndefined();
  });
});
