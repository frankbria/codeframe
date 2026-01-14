const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8080';

export interface AuthTokens {
  access_token: string;
  token_type: string;
}

export interface User {
  id: number;
  email: string;
  name?: string;
  is_active: boolean;
  is_superuser: boolean;
  is_verified: boolean;
}

export interface LoginCredentials {
  username: string;  // fastapi-users expects 'username' field
  password: string;
}

export interface RegisterData {
  email: string;
  password: string;
  name?: string;
}

export async function login(email: string, password: string): Promise<AuthTokens> {
  const formData = new URLSearchParams();
  formData.append('username', email);
  formData.append('password', password);

  const res = await fetch(`${API_URL}/auth/jwt/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: formData,
  });

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: 'Login failed' }));
    throw new Error(error.detail || 'Login failed');
  }
  
  return res.json();
}

export async function register(data: RegisterData): Promise<User> {
  const res = await fetch(`${API_URL}/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: 'Registration failed' }));
    throw new Error(error.detail || 'Registration failed');
  }
  
  return res.json();
}

export async function getCurrentUser(token: string): Promise<User> {
  const res = await fetch(`${API_URL}/users/me`, {
    headers: { Authorization: `Bearer ${token}` },
  });

  if (!res.ok) {
    throw new Error('Failed to get user');
  }
  
  return res.json();
}

export async function logout(token: string): Promise<void> {
  // JWT logout is client-side only (delete token)
  // Optional: call backend to invalidate token if using token blacklist
  await fetch(`${API_URL}/auth/jwt/logout`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
  });
}

export async function authenticatedFetch(
  url: string,
  options: RequestInit = {}
): Promise<Response> {
  const token = localStorage.getItem('auth_token');

  if (!token) {
    throw new Error('Not authenticated');
  }

  const headers = new Headers(options.headers);
  headers.set('Authorization', `Bearer ${token}`);

  return fetch(url, {
    ...options,
    headers,
  });
}

/**
 * Convenience wrapper for authenticated JSON API requests.
 * Automatically sets Content-Type and Authorization headers.
 */
export async function authFetch<T = unknown>(
  url: string,
  options: {
    method?: 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH';
    body?: unknown;
    signal?: AbortSignal;
  } = {}
): Promise<T> {
  const token = localStorage.getItem('auth_token');

  if (!token) {
    throw new Error('Not authenticated');
  }

  const headers: HeadersInit = {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${token}`,
  };

  const response = await fetch(url, {
    method: options.method || 'GET',
    headers,
    body: options.body ? JSON.stringify(options.body) : undefined,
    signal: options.signal,
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(
      `Request failed: ${response.status} ${errorText}`
    );
  }

  // Handle empty responses (204 No Content, etc.)
  const text = await response.text();
  if (!text) {
    return {} as T;
  }

  return JSON.parse(text) as T;
}
