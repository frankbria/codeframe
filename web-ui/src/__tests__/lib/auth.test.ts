/**
 * Tests for the frontend auth library (issue #336).
 *
 * Covers token storage (localStorage key `auth_token`, SSR-safe),
 * login (form-encoded POST /auth/jwt/login), register (bootstrap-first-user),
 * logout (clear + redirect), the `withStreamTicket` SSE/WS helper (#745), and
 * friendly error normalization for bad credentials / closed registration.
 */
import axios from 'axios';

jest.mock('axios');
const mockedAxios = axios as jest.Mocked<typeof axios>;

// jsdom 30 makes window.location non-configurable; mock the navigation seam so
// logout's redirect is observable without emitting a jsdom navigation error.
jest.mock('@/lib/navigation', () => ({
  currentPathname: jest.fn(() => ''),
  redirectTo: jest.fn(),
}));

import {
  getToken,
  setToken,
  clearToken,
  login,
  register,
  logout,
  withStreamTicket,
} from '@/lib/auth';
import { redirectTo } from '@/lib/navigation';

const mockRedirectTo = redirectTo as jest.MockedFunction<typeof redirectTo>;

describe('auth token storage', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('setToken stores under the `auth_token` key and getToken reads it', () => {
    setToken('jwt-abc');
    expect(localStorage.getItem('auth_token')).toBe('jwt-abc');
    expect(getToken()).toBe('jwt-abc');
  });

  it('getToken returns null when no token stored', () => {
    expect(getToken()).toBeNull();
  });

  it('clearToken removes the token', () => {
    setToken('jwt-abc');
    clearToken();
    expect(getToken()).toBeNull();
  });
});

describe('login', () => {
  beforeEach(() => {
    localStorage.clear();
    jest.clearAllMocks();
  });

  it('POSTs form-encoded credentials and stores the returned token', async () => {
    mockedAxios.post.mockResolvedValueOnce({
      data: { access_token: 'jwt-login', token_type: 'bearer' },
    });

    const token = await login('user@example.com', 'pw123');

    expect(token).toBe('jwt-login');
    expect(getToken()).toBe('jwt-login');

    expect(mockedAxios.post).toHaveBeenCalledTimes(1);
    const [url, body, config] = mockedAxios.post.mock.calls[0];
    expect(url).toContain('/auth/jwt/login');
    // Body must be form-encoded (URLSearchParams) with username/password.
    // Parse rather than substring-match so the assertion doesn't embed a
    // "password=..." literal (GitGuardian generic-password false positive).
    const params = new URLSearchParams(
      body instanceof URLSearchParams ? body.toString() : String(body)
    );
    expect(params.get('username')).toBe('user@example.com');
    expect(params.get('password')).toBe('pw123');
    expect(config?.headers?.['Content-Type']).toBe(
      'application/x-www-form-urlencoded'
    );
  });

  it('throws a friendly message on bad credentials (400)', async () => {
    mockedAxios.post.mockRejectedValueOnce({
      response: { status: 400, data: { detail: 'LOGIN_BAD_CREDENTIALS' } },
    });
    mockedAxios.isAxiosError = jest.fn(() => true) as unknown as typeof axios.isAxiosError;

    await expect(login('user@example.com', 'wrong')).rejects.toThrow(
      /invalid email or password/i
    );
  });
});

describe('register', () => {
  beforeEach(() => {
    localStorage.clear();
    jest.clearAllMocks();
  });

  it('POSTs JSON to /auth/register', async () => {
    mockedAxios.post.mockResolvedValueOnce({
      data: { id: '1', email: 'first@example.com' },
    });

    await register('first@example.com', 'pw123');

    const [url, body] = mockedAxios.post.mock.calls[0];
    expect(url).toContain('/auth/register');
    expect(body).toEqual({ email: 'first@example.com', password: 'pw123' });
  });

  it('throws "registration is closed" on 403', async () => {
    mockedAxios.post.mockRejectedValueOnce({
      response: { status: 403, data: { detail: 'forbidden' } },
    });
    mockedAxios.isAxiosError = jest.fn(() => true) as unknown as typeof axios.isAxiosError;

    await expect(register('second@example.com', 'pw')).rejects.toThrow(
      /registration is closed/i
    );
  });
});

describe('logout', () => {
  beforeEach(() => {
    localStorage.clear();
    mockRedirectTo.mockClear();
  });

  it('clears the token and redirects to /login', () => {
    setToken('jwt-abc');
    logout();
    expect(getToken()).toBeNull();
    expect(mockRedirectTo).toHaveBeenCalledWith('/login');
  });
});

describe('withStreamTicket', () => {
  it('returns the URL unchanged when the injected fetcher resolves null', async () => {
    const fetchTicket = jest.fn().mockResolvedValue(null);
    await expect(
      withStreamTicket('http://x/api/v2/stream', fetchTicket)
    ).resolves.toBe('http://x/api/v2/stream');
  });

  it('appends ticket with `?` when URL has no query string', async () => {
    const fetchTicket = jest.fn().mockResolvedValue('tk-xyz');
    await expect(
      withStreamTicket('http://x/api/v2/stream', fetchTicket)
    ).resolves.toBe('http://x/api/v2/stream?ticket=tk-xyz');
  });

  it('appends ticket with `&` when URL already has a query string', async () => {
    const fetchTicket = jest.fn().mockResolvedValue('tk-xyz');
    await expect(
      withStreamTicket(
        'http://x/api/v2/stream?workspace_path=%2Ftmp',
        fetchTicket
      )
    ).resolves.toBe('http://x/api/v2/stream?workspace_path=%2Ftmp&ticket=tk-xyz');
  });

  it('URL-encodes the ticket value', async () => {
    const fetchTicket = jest.fn().mockResolvedValue('a b/c');
    await expect(withStreamTicket('http://x/s', fetchTicket)).resolves.toBe(
      'http://x/s?ticket=a%20b%2Fc'
    );
  });

  it('calls the injected fetcher fresh on every invocation (single-use tickets)', async () => {
    const fetchTicket = jest.fn().mockResolvedValue('tk-1');
    await withStreamTicket('http://x/s', fetchTicket);
    await withStreamTicket('http://x/s', fetchTicket);
    expect(fetchTicket).toHaveBeenCalledTimes(2);
  });
});
