'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import useSWR from 'swr';
import { toast } from 'sonner';

import { settingsApi } from '@/lib/api';
import { getSelectedWorkspacePath } from '@/lib/workspace-storage';
import type { AgentSettings, AgentTypeKey, ApiError } from '@/types';
import { ApiKeysTab } from '@/components/settings/ApiKeysTab';
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

const AGENT_TYPE_LABELS: Record<AgentTypeKey, string> = {
  claude_code: 'Claude Code',
  codex: 'Codex',
  opencode: 'OpenCode',
  react: 'ReAct',
};

const MODEL_OPTIONS_BY_AGENT: Record<AgentTypeKey, string[]> = {
  claude_code: ['claude-opus-4', 'claude-sonnet-4', 'claude-haiku-4'],
  codex: ['gpt-4o', 'gpt-4o-mini', 'o3', 'o3-mini'],
  opencode: ['claude-opus-4', 'claude-sonnet-4', 'gpt-4o'],
  react: ['claude-opus-4', 'claude-sonnet-4', 'gpt-4o', 'qwen2.5-coder:7b'],
};

const UNSET_MODEL_VALUE = '__unset__';

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
      setDraft({
        ...data,
        agent_models: data.agent_models.map((m) => ({ ...m })),
      });
    }
  }, [data]);

  if (!workspaceReady) return null;

  const updateAgentModel = (agentType: AgentTypeKey, model: string) => {
    if (!draft) return;
    setDraft({
      ...draft,
      agent_models: draft.agent_models.map((entry) =>
        entry.agent_type === agentType
          ? { ...entry, default_model: model }
          : entry
      ),
    });
  };

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
    setDraft({
      ...data,
      agent_models: data.agent_models.map((m) => ({ ...m })),
    });
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
            <TabsTrigger value="proof9">PROOF9</TabsTrigger>
            <TabsTrigger value="workspace">Workspace</TabsTrigger>
          </TabsList>

          <TabsContent value="agent">
            <section className="rounded-lg border bg-card p-6">
              <h2 className="mb-1 text-lg font-semibold">Agent Settings</h2>
              <p className="mb-6 text-sm text-muted-foreground">
                Default model per agent type, plus per-task limits.
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
                  onModelChange={updateAgentModel}
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
                <ComingSoon />
              )}
            </section>
          </TabsContent>

          <TabsContent value="api-keys">
            <section className="rounded-lg border bg-card p-6">
              <h2 className="mb-1 text-lg font-semibold">API Keys</h2>
              <ApiKeysTab />
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

function ComingSoon() {
  return <p className="text-sm text-muted-foreground">Coming soon</p>;
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
  onModelChange: (agentType: AgentTypeKey, model: string) => void;
  onMaxTurnsChange: (value: number) => void;
  onMaxCostChange: (value: number | null) => void;
  onSave: () => void;
  onDiscard: () => void;
  saving: boolean;
}

function AgentSettingsForm({
  draft,
  onModelChange,
  onMaxTurnsChange,
  onMaxCostChange,
  onSave,
  onDiscard,
  saving,
}: AgentSettingsFormProps) {
  return (
    <div className="space-y-6">
      <div>
        <h3 className="mb-3 text-sm font-medium">Default model per agent type</h3>
        <div className="space-y-3">
          {draft.agent_models.map((entry) => {
            const label = AGENT_TYPE_LABELS[entry.agent_type as AgentTypeKey] ?? entry.agent_type;
            const options = MODEL_OPTIONS_BY_AGENT[entry.agent_type as AgentTypeKey] ?? [];
            const selectValue = entry.default_model || UNSET_MODEL_VALUE;
            return (
              <div
                key={entry.agent_type}
                className="grid grid-cols-1 items-center gap-2 sm:grid-cols-[180px_1fr]"
              >
                <label
                  htmlFor={`model-${entry.agent_type}`}
                  className="text-sm text-muted-foreground"
                >
                  {label}
                </label>
                <Select
                  value={selectValue}
                  onValueChange={(value) =>
                    onModelChange(
                      entry.agent_type as AgentTypeKey,
                      value === UNSET_MODEL_VALUE ? '' : value
                    )
                  }
                >
                  <SelectTrigger id={`model-${entry.agent_type}`}>
                    <SelectValue placeholder="Select model" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={UNSET_MODEL_VALUE}>(default)</SelectItem>
                    {options.map((model) => (
                      <SelectItem key={model} value={model}>
                        {model}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            );
          })}
        </div>
      </div>

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
