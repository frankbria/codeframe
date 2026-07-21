'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { HugeiconsIcon } from '@hugeicons/react';
import { Login01Icon, Mail01Icon, LockIcon, Loading03Icon } from '@hugeicons/core-free-icons';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
  CardFooter,
} from '@/components/ui/card';
import { login, register, isAuthenticated } from '@/lib/auth';

type Mode = 'login' | 'register';

/**
 * Authentication page (issue #336). Renders bare — no sidebar — because
 * `AppLayout` short-circuits the shell on the `/login` route.
 *
 * Two modes:
 * - login: email + password → JWT, redirect to `/`.
 * - register: bootstrap-first-user; on success auto-logs-in, then redirects.
 */
export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  // Already-authenticated visitors are bounced to the app (#651). Tracked in
  // state so we render a neutral loader (not a flash of the form) while the
  // client-side redirect runs.
  const [redirecting, setRedirecting] = useState(false);

  useEffect(() => {
    if (isAuthenticated()) {
      setRedirecting(true);
      router.replace('/');
    }
  }, [router]);

  const isRegister = mode === 'register';

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      if (isRegister) {
        await register(email, password);
        // First account created — log in immediately for a seamless handoff.
        await login(email, password);
      } else {
        await login(email, password);
      }
      router.push('/');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong.');
    } finally {
      setSubmitting(false);
    }
  }

  function toggleMode() {
    setMode((prev) => (prev === 'login' ? 'register' : 'login'));
    setError(null);
  }

  if (redirecting) {
    return (
      <div
        className="flex min-h-screen items-center justify-center bg-background p-4"
        role="status"
        aria-label="Redirecting"
      >
        <HugeiconsIcon icon={Loading03Icon} className="h-6 w-6 animate-spin text-muted-foreground" aria-hidden="true" />
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-4">
      <Card className="w-full max-w-sm">
        <CardHeader className="space-y-1.5">
          <div className="flex items-center gap-2">
            <HugeiconsIcon icon={Login01Icon} className="h-5 w-5 text-primary" aria-hidden="true" />
            <CardTitle>{isRegister ? 'Create your account' : 'Sign in'}</CardTitle>
          </div>
          <CardDescription>
            {isRegister
              ? 'Set up the first CodeFRAME account to get started.'
              : 'Sign in to access your CodeFRAME workspace.'}
          </CardDescription>
        </CardHeader>

        <form onSubmit={handleSubmit}>
          <CardContent className="space-y-4">
            {error && (
              <div
                role="alert"
                className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive"
              >
                {error}
              </div>
            )}

            <div className="space-y-1.5">
              <label
                htmlFor="email"
                className="flex items-center gap-1.5 text-sm font-medium text-foreground"
              >
                <HugeiconsIcon icon={Mail01Icon} className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
                Email
              </label>
              <Input
                id="email"
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                disabled={submitting}
              />
            </div>

            <div className="space-y-1.5">
              <label
                htmlFor="password"
                className="flex items-center gap-1.5 text-sm font-medium text-foreground"
              >
                <HugeiconsIcon icon={LockIcon} className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
                Password
              </label>
              <Input
                id="password"
                type="password"
                autoComplete={isRegister ? 'new-password' : 'current-password'}
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                disabled={submitting}
              />
            </div>
          </CardContent>

          <CardFooter className="flex flex-col gap-3">
            <Button type="submit" className="w-full" disabled={submitting}>
              {submitting && (
                <HugeiconsIcon icon={Loading03Icon} className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" />
              )}
              {isRegister ? 'Create account' : 'Sign in'}
            </Button>
            <button
              type="button"
              onClick={toggleMode}
              className="text-sm text-muted-foreground transition-colors hover:text-foreground"
            >
              {isRegister
                ? 'Already have an account? Sign in'
                : 'First time here? Create the first account'}
            </button>
          </CardFooter>
        </form>
      </Card>
    </div>
  );
}
