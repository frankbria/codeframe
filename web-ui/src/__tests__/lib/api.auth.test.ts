/**
 * Tests for the auth behavior of the shared axios client (issue #336):
 * - request interceptor attaches `Authorization: Bearer <token>` when present;
 * - response interceptor on 401 clears the token and redirects to /login,
 *   except when already on /login (and the existing error normalization stays
 *   intact).
 *
 * We exercise the interceptors directly off the exported axios instance so we
 * don't need a live server.
 */
import type { InternalAxiosRequestConfig, AxiosError } from 'axios';
import { AxiosHeaders } from 'axios';

import api from '@/lib/api';
import { setToken, getToken } from '@/lib/auth';
import { currentPathname, redirectTo } from '@/lib/navigation';

// jsdom 30 makes window.location non-configurable, so we mock the navigation
// seam (src/lib/navigation) to control pathname and observe redirects instead.
jest.mock('@/lib/navigation', () => ({
  currentPathname: jest.fn(() => '/tasks'),
  redirectTo: jest.fn(),
}));

const mockCurrentPathname = currentPathname as jest.MockedFunction<typeof currentPathname>;
const mockRedirectTo = redirectTo as jest.MockedFunction<typeof redirectTo>;

// Pull the registered handlers off the axios instance interceptor stacks.
function getRequestHandler() {
  // @ts-expect-error - axios keeps handlers on a private `.handlers` array
  const handlers = api.interceptors.request.handlers as Array<{
    fulfilled: (c: InternalAxiosRequestConfig) => InternalAxiosRequestConfig;
  }>;
  return handlers.find((h) => h && h.fulfilled)!.fulfilled;
}

function getResponseRejectHandler() {
  // @ts-expect-error - private handlers array
  const handlers = api.interceptors.response.handlers as Array<{
    rejected: (e: AxiosError) => Promise<never>;
  }>;
  return handlers.find((h) => h && h.rejected)!.rejected;
}

describe('api request interceptor — Authorization header', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('attaches Bearer token when a token is stored', () => {
    setToken('jwt-123');
    const handler = getRequestHandler();
    const config = handler({
      headers: new AxiosHeaders(),
    } as InternalAxiosRequestConfig);
    expect(config.headers.Authorization).toBe('Bearer jwt-123');
  });

  it('does not attach Authorization when no token is stored', () => {
    const handler = getRequestHandler();
    const config = handler({
      headers: new AxiosHeaders(),
    } as InternalAxiosRequestConfig);
    expect(config.headers.Authorization).toBeUndefined();
  });
});

describe('api response interceptor — 401 handling', () => {
  beforeEach(() => {
    localStorage.clear();
    mockRedirectTo.mockClear();
    mockCurrentPathname.mockReturnValue('/tasks');
  });

  it('clears token and redirects to /login on 401', async () => {
    setToken('jwt-123');
    const handler = getResponseRejectHandler();

    await expect(
      handler({
        message: 'Unauthorized',
        response: { status: 401, data: { detail: 'Unauthorized' } },
      } as AxiosError)
    ).rejects.toMatchObject({ status_code: 401 });

    expect(getToken()).toBeNull();
    expect(mockRedirectTo).toHaveBeenCalledWith('/login');
  });

  it('does NOT redirect when already on /login', async () => {
    mockCurrentPathname.mockReturnValue('/login');
    setToken('jwt-123');
    const handler = getResponseRejectHandler();

    await expect(
      handler({
        message: 'Unauthorized',
        response: { status: 401, data: { detail: 'bad' } },
      } as AxiosError)
    ).rejects.toBeDefined();

    expect(mockRedirectTo).not.toHaveBeenCalled();
  });

  it('preserves error normalization for non-401 errors', async () => {
    const handler = getResponseRejectHandler();
    await expect(
      handler({
        message: 'Server error',
        response: { status: 500, data: { detail: 'Boom' } },
      } as AxiosError)
    ).rejects.toMatchObject({ detail: 'Boom', status_code: 500 });
    expect(mockRedirectTo).not.toHaveBeenCalled();
  });
});
