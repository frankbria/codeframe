import useSWR from 'swr';
import { authApi } from '@/lib/api';

/**
 * True only when the server has said this session lacks `admin` scope (#1255).
 *
 * Admin-only actions (merge, PR create, credential and PAT storage) are
 * disabled and explained rather than hidden. Loading and a failed probe return
 * false: the server's 403 stays the authority, and a flaky probe must not lock
 * the auth-off local operator out of their own instance.
 */
export function useAdminDenied(): boolean {
  const { data } = useSWR('/auth/me', () => authApi.getMe(), { revalidateOnFocus: false });
  return data?.is_admin === false;
}
