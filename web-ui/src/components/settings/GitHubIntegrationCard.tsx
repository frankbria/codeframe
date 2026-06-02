'use client';

import { useState } from 'react';
import useSWR from 'swr';
import { toast } from 'sonner';

import { integrationsApi } from '@/lib/api';
import type { ApiError, GitHubIntegrationStatus } from '@/types';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

interface GitHubIntegrationCardProps {
  workspacePath: string | null;
}

export function GitHubIntegrationCard({
  workspacePath,
}: GitHubIntegrationCardProps) {
  const swrKey = workspacePath
    ? ['github-integration', workspacePath]
    : null;
  const { data, error, mutate } = useSWR<GitHubIntegrationStatus>(
    swrKey,
    () => integrationsApi.getStatus(workspacePath!)
  );

  const [pat, setPat] = useState('');
  const [repo, setRepo] = useState('');
  const [working, setWorking] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  if (!workspacePath) {
    return (
      <p className="text-sm text-muted-foreground">
        Select a workspace from the sidebar to connect a GitHub repository.
      </p>
    );
  }
  if (error) {
    return (
      <p className="text-sm text-destructive">
        Failed to load GitHub integration status. Check the server logs.
      </p>
    );
  }
  if (!data) {
    return <p className="text-sm text-muted-foreground">Loading…</p>;
  }

  const handleConnect = async () => {
    if (!pat || !repo) return;
    setWorking(true);
    setFormError(null);
    try {
      const result = await integrationsApi.connect(workspacePath, pat, repo);
      await mutate(
        {
          connected: true,
          repo: result.repo,
          owner_login: result.owner_login,
          owner_avatar_url: result.owner_avatar_url,
        },
        { revalidate: false }
      );
      setPat('');
      setRepo('');
      toast.success(`Connected to ${result.repo}`);
    } catch (err) {
      const detail =
        (err as ApiError).detail || 'Failed to connect. Check the token and repo.';
      setFormError(detail);
      toast.error(detail);
    } finally {
      setWorking(false);
    }
  };

  const handleDisconnect = async () => {
    setWorking(true);
    try {
      await integrationsApi.disconnect(workspacePath);
      await mutate(
        {
          connected: false,
          repo: null,
          owner_login: null,
          owner_avatar_url: null,
        },
        { revalidate: false }
      );
      toast.success('Disconnected from GitHub');
    } catch (err) {
      toast.error((err as ApiError).detail || 'Failed to disconnect');
    } finally {
      setWorking(false);
    }
  };

  if (data.connected) {
    return (
      <div className="space-y-4" data-state="connected">
        <div className="flex items-center gap-3 rounded-lg border bg-card p-4">
          {data.owner_avatar_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={data.owner_avatar_url}
              alt={`${data.owner_login ?? 'owner'} avatar`}
              className="h-10 w-10 rounded-full"
            />
          ) : null}
          <div className="min-w-0">
            <p className="text-sm font-medium text-green-600">
              ✓ Connected to GitHub
            </p>
            <p className="truncate text-sm">{data.repo}</p>
          </div>
        </div>
        <Button
          type="button"
          variant="destructive"
          onClick={handleDisconnect}
          disabled={working}
        >
          {working ? 'Disconnecting…' : 'Disconnect'}
        </Button>
      </div>
    );
  }

  const canConnect = !!pat && !!repo && !working;

  return (
    <div className="space-y-4" data-state="disconnected">
      <p className="text-sm text-muted-foreground">
        Connect a GitHub repository with a Personal Access Token to import its
        issues. The token is stored encrypted on this machine and never shown
        again.
      </p>

      <div>
        <label
          htmlFor="github-pat"
          className="mb-1 block text-sm font-medium"
        >
          Personal Access Token
        </label>
        <Input
          id="github-pat"
          type="password"
          autoComplete="off"
          spellCheck={false}
          placeholder="ghp_… or github_pat_…"
          value={pat}
          onChange={(e) => setPat(e.target.value)}
          disabled={working}
          aria-label="Personal Access Token"
        />
      </div>

      <div>
        <label
          htmlFor="github-repo"
          className="mb-1 block text-sm font-medium"
        >
          Repository (owner/repo)
        </label>
        <Input
          id="github-repo"
          type="text"
          placeholder="acme-corp/my-app"
          value={repo}
          onChange={(e) => setRepo(e.target.value)}
          disabled={working}
          aria-label="Repository"
        />
      </div>

      <Button type="button" onClick={handleConnect} disabled={!canConnect}>
        {working ? 'Connecting…' : 'Connect'}
      </Button>

      {formError && (
        <p className="text-sm text-destructive" role="alert">
          ⚠ {formError}
        </p>
      )}
    </div>
  );
}
