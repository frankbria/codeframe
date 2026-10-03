'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import useSWR from 'swr';
import { toast } from 'sonner';

import { settingsApi } from '@/lib/api';
import { getSelectedWorkspacePath } from '@/lib/workspace-storage';
import type { AgentSettings, ApiError } from '@/types';
import { ApiKeysTab } from '@/components/settings/ApiKeysTab';
import { GitHubIntegrationCard } from '@/components/settings/GitHubIntegrationCard';
import { NotificationsTab } from '@/components/settings/NotificationsTab';
import { Proof9DefaultsTab } from '@/components/settings/Proof9DefaultsTab';
import { WorkspaceConfigTab } from '@/components/settings/WorkspaceConfigTab';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from '@/components/ui/tabs';

export default function SettingsPage() {
  const [workspacePath, setWorkspacePath] = useState<string | null>(null);
  const [workspaceReady, setWorkspaceReady] = useState(false);

  useEffect(() => {
    setWorkspacePath(getSelectedWorkspacePath());
    setWorkspaceReady(true);
  }, []);

  const swrKey = workspacePath ? ['settings', workspacePath] : null;
  const { data, error, isLoading, mutate } = useSWR<AgentSettings>(
    swrKey,
    () => settingsApi.get(workspacePath!)
  );

  const [draft, setDraft] = useState<AgentSettings | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (data) {
      setDraft({ ...data });
    }
  }, [data]);

  if (!workspaceReady) return null;

  const handleSave = async () => {
    if (!draft || !workspacePath) return;
    setSaving(true);
    try {
      const saved = await settingsApi.update(workspacePath, draft);
      await mutate(saved, { revalidate: false });
      toast.success('Settings saved');
    } catch (err) {
      const apiError = err as ApiError;
      toast.error(apiError.detail || 'Failed to save settings');
    } finally {
      setSaving(false);
    }
  };

  const handleDiscard = () => {
    if (!data) return;
    setDraft({ ...data });
    toast.info('Changes discarded');
  };

  return (
    <main className="min-h-screen bg-background">
      <div className="mx-auto max-w-5xl px-4 py-8">
        <h1 className="mb-6 text-2xl font-bold">Settings</h1>

        <Tabs defaultValue="agent" className="w-full">
          <TabsList className="mb-6">
            <TabsTrigger value="agent">Agent</TabsTrigger>
            <TabsTrigger value="api-keys">API Keys</TabsTrigger>
            <TabsTrigger value="integrations">Integrations</TabsTrigger>
            <TabsTrigger value="notifications">Notifications</TabsTrigger>
            <TabsTrigger value="proof9">PROOF9</TabsTrigger>
            <TabsTrigger value="workspace">Workspace</TabsTrigger>
          </TabsList>

          <TabsContent value="agent">
            <section className="rounded-lg border bg-card p-6">
              <h2 className="mb-1 text-lg font-semibold">Agent Settings</h2>
              <p className="mb-6 text-sm text-muted-foreground">
                Per-task limits for agent runs.
              </p>

              {!workspacePath ? (
                <NoWorkspaceMessage />
              ) : isLoading && !draft ? (
                <p className="text-sm text-muted-foreground">Loading…</p>
              ) : error ? (
                <p className="text-sm text-destructive">
                  Failed to load settings.
                </p>
              ) : draft ? (
                <AgentSettingsForm
                  draft={draft}
                  onMaxTurnsChange={(v) =>
                    setDraft({ ...draft, max_turns: v })
                  }
                  onMaxCostChange={(v) =>
                    setDraft({ ...draft, max_cost_usd: v })
                  }
                  onSave={handleSave}
                  onDiscard={handleDiscard}
                  saving={saving}
                />
              ) : (
                <p className="text-sm text-muted-foreground">Loading…</p>
              )}
            </section>
          </TabsContent>

          <TabsContent value="api-keys">
            <section className="rounded-lg border bg-card p-6">
              <h2 className="mb-1 text-lg font-semibold">API Keys</h2>
              <ApiKeysTab />
            </section>
          </TabsContent>

          <TabsContent value="integrations">
            <section className="rounded-lg border bg-card p-6">
              <h2 className="mb-1 text-lg font-semibold">Integrations</h2>
              <p className="mb-6 text-sm text-muted-foreground">
                Connect a GitHub repository to import its issues.
              </p>
              <GitHubIntegrationCard workspacePath={workspacePath} />
            </section>
          </TabsContent>

          <TabsContent value="notifications">
            <section className="rounded-lg border bg-card p-6">
              <h2 className="mb-1 text-lg font-semibold">Notifications</h2>
              <p className="mb-6 text-sm text-muted-foreground">
                Outbound webhook for batch, blocker, and PR-merge events.
              </p>
              <NotificationsTab workspacePath={workspacePath} />
            </section>
          </TabsContent>

          <TabsContent value="proof9">
            <section className="rounded-lg border bg-card p-6">
              <h2 className="mb-1 text-lg font-semibold">PROOF9 Defaults</h2>
              <p className="mb-6 text-sm text-muted-foreground">
                Gate enablement and strictness for this workspace.
              </p>
              <Proof9DefaultsTab workspacePath={workspacePath} />
            </section>
          </TabsContent>

          <TabsContent value="workspace">
            <section className="rounded-lg border bg-card p-6">
              <h2 className="mb-1 text-lg font-semibold">Workspace Configuration</h2>
              <p className="mb-6 text-sm text-muted-foreground">
                Root path, default branch, and tech-stack auto-detection.
              </p>
              <WorkspaceConfigTab workspacePath={workspacePath} />
            </section>
          </TabsContent>
        </Tabs>
      </div>
    </main>
  );
}

function NoWorkspaceMessage() {
  return (
    <div className="rounded-lg border bg-muted/50 p-6 text-center">
      <p className="text-sm text-muted-foreground">
        No workspace selected. Use the sidebar to return to{' '}
        <Link href="/" className="text-primary hover:underline">
          Workspace
        </Link>{' '}
        and select a project to manage agent settings.
      </p>
    </div>
  );
}

interface AgentSettingsFormProps {
  draft: AgentSettings;
  onMaxTurnsChange: (value: number) => void;
  onMaxCostChange: (value: number | null) => void;
  onSave: () => void;
  onDiscard: () => void;
  saving: boolean;
}

function AgentSettingsForm({
  draft,
  onMaxTurnsChange,
  onMaxCostChange,
  onSave,
  onDiscard,
  saving,
}: AgentSettingsFormProps) {
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div>
          <label
            htmlFor="max-turns"
            className="mb-1 block text-sm font-medium"
          >
            Max turns per task
          </label>
          <Input
            id="max-turns"
            type="number"
            min={1}
            value={draft.max_turns}
            onChange={(e) => {
              const v = Number.parseInt(e.target.value, 10);
              if (!Number.isNaN(v)) onMaxTurnsChange(v);
            }}
          />
        </div>
        <div>
          <label
            htmlFor="max-cost"
            className="mb-1 block text-sm font-medium"
          >
            Max cost per task (USD)
          </label>
          <Input
            id="max-cost"
            type="number"
            min={0}
            step="0.01"
            value={draft.max_cost_usd ?? ''}
            placeholder="No limit"
            onChange={(e) => {
              const raw = e.target.value;
              if (raw === '') {
                onMaxCostChange(null);
                return;
              }
              const v = Number.parseFloat(raw);
              if (!Number.isNaN(v)) onMaxCostChange(v);
            }}
          />
          <p className="mt-1 text-xs text-muted-foreground">
            Stops the run and raises a blocker once estimated spend reaches the
            cap. Applies to the built-in agent; delegated engines (Claude Code,
            Codex, OpenCode) bill through their own CLI and are not counted.
          </p>
        </div>
      </div>

      <div className="flex justify-end gap-2 border-t pt-4">
        <Button
          type="button"
          variant="outline"
          onClick={onDiscard}
          disabled={saving}
        >
          Discard
        </Button>
        <Button type="button" onClick={onSave} disabled={saving}>
          {saving ? 'Saving…' : 'Save'}
        </Button>
      </div>
    </div>
  );
}
