/**
 * Tests for the auth probes (#651):
 * - `verifyAuthAfterStreamFailure` (SSE/WS re-auth) uses the shared client.
 * - `checkAuthAccess` (route-guard) uses a bare axios call so the global 401
 *   interceptor does not fire.
 *
 * Both hit the auth-mode-aware `/api/v2/settings/keys` endpoint, NOT the
 * fastapi-users `/users/me` (which 401s even when auth is disabled). Isolated in
 * its own file so the axios mock doesn't affect api.auth.test.ts (which pokes
 * the real interceptors).
 */
const mockInstanceGet = jest.fn();
const mockBareGet = jest.fn();
let mockIsAxiosError: (e: unknown) => boolean = () => false;

jest.mock('axios', () => {
  const instance = {
    get: (...args: unknown[]) => mockInstanceGet(...args),
    interceptors: {
      request: { use: jest.fn() },
      response: { use: jest.fn() },
    },
  };
  return {
    __esModule: true,
    default: {
      create: jest.fn(() => instance),
      get: (...args: unknown[]) => mockBareGet(...args),
      isAxiosError: (e: unknown) => mockIsAxiosError(e),
    },
    isAxiosError: (e: unknown) => mockIsAxiosError(e),
  };
});

import { verifyAuthAfterStreamFailure, checkAuthAccess } from '@/lib/api';

const PROBE_PATH = '/api/v2/settings/keys';

describe('verifyAuthAfterStreamFailure', () => {
  beforeEach(() => {
    mockInstanceGet.mockReset();
  });

  it('probes the auth-mode-aware endpoint via the shared (intercepted) client', async () => {
    mockInstanceGet.mockResolvedValue({ data: [] });
    await verifyAuthAfterStreamFailure();
    expect(mockInstanceGet).toHaveBeenCalledWith(PROBE_PATH);
  });

  it('resolves (never throws) when the probe succeeds', async () => {
    mockInstanceGet.mockResolvedValue({ data: [] });
    await expect(verifyAuthAfterStreamFailure()).resolves.toBeUndefined();
  });

  it('swallows probe errors so callers can fire-and-forget', async () => {
    mockInstanceGet.mockRejectedValue(new Error('401'));
    await expect(verifyAuthAfterStreamFailure()).resolves.toBeUndefined();
  });
});

describe('checkAuthAccess', () => {
  beforeEach(() => {
    mockBareGet.mockReset();
    mockIsAxiosError = () => false;
    localStorage.clear();
  });

  it('returns "allowed" on a 2xx (valid token or auth disabled)', async () => {
    mockBareGet.mockResolvedValue({ data: [] });
    await expect(checkAuthAccess()).resolves.toBe('allowed');
    expect(mockBareGet).toHaveBeenCalledWith(
      expect.stringContaining(PROBE_PATH),
      expect.objectContaining({ withCredentials: true })
    );
  });

  it('returns "denied" on a 401 (auth required, unauthenticated)', async () => {
    mockIsAxiosError = () => true;
    mockBareGet.mockRejectedValue({ response: { status: 401 } });
    await expect(checkAuthAccess()).resolves.toBe('denied');
  });

  it('returns "error" on a network/other failure (fail open)', async () => {
    mockIsAxiosError = () => true;
    mockBareGet.mockRejectedValue({ response: { status: 503 } });
    await expect(checkAuthAccess()).resolves.toBe('error');
  });

  it('returns "error" on a non-axios failure', async () => {
    mockIsAxiosError = () => false;
    mockBareGet.mockRejectedValue(new Error('boom'));
    await expect(checkAuthAccess()).resolves.toBe('error');
  });
});
