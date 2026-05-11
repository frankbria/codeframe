'use client';

import { useEffect, useState } from 'react';
import useSWR from 'swr';
import { toast } from 'sonner';

import { workspaceConfigApi } from '@/lib/api';
import type {
  ApiError,
  WorkspaceConfigResponse,
} from '@/types';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';

interface WorkspaceConfigTabProps {
  workspacePath: string | null;
}

function isDirty(
  a: WorkspaceConfigResponse,
  b: WorkspaceConfigResponse
): boolean {
  return (
    a.workspace_root !== b.workspace_root ||
    a.default_branch !== b.default_branch ||
    a.auto_detect_tech_stack !== b.auto_detect_tech_stack ||
    (a.tech_stack_override ?? '') !== (b.tech_stack_override ?? '')
  );
}

export function WorkspaceConfigTab({ workspacePath }: WorkspaceConfigTabProps) {
  const swrKey = workspacePath ? ['workspace-config', workspacePath] : null;
  const { data, error, mutate } = useSWR<WorkspaceConfigResponse>(
    swrKey,
    () => workspaceConfigApi.getConfig(workspacePath!)
  );

  const [draft, setDraft] = useState<WorkspaceConfigResponse | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (data) {
      setDraft({ ...data });
    }
  }, [data]);

  if (!workspacePath) {
    return (
      <p className="text-sm text-muted-foreground">
        Select a workspace from the sidebar to manage workspace configuration.
      </p>
    );
  }
  if (error) {
    return (
      <p className="text-sm text-destructive">
        Failed to load workspace config. Check the server logs.
      </p>
    );
  }
  if (!data || !draft) {
    return <p className="text-sm text-muted-foreground">Loading…</p>;
  }

  const dirty = isDirty(data, draft);
  const canSave = dirty && !saving && draft.workspace_root.trim() !== '' && draft.default_branch.trim() !== '';

  const handleSave = async () => {
    setSaving(true);
    try {
      const saved = await workspaceConfigApi.updateConfig(workspacePath, {
        workspace_root: draft.workspace_root,
        default_branch: draft.default_branch,
        auto_detect_tech_stack: draft.auto_detect_tech_stack,
        tech_stack_override: draft.tech_stack_override,
      });
      await mutate(saved, { revalidate: false });
      toast.success('Workspace config saved');
    } catch (err) {
      const apiError = err as ApiError;
      toast.error(apiError.detail || 'Failed to save workspace config');
    } finally {
      setSaving(false);
    }
  };

  const handleDiscard = () => {
    setDraft({ ...data });
    toast.info('Changes discarded');
  };

  return (
    <div className="space-y-6">
      <div>
        <label
          htmlFor="workspace-root"
          className="mb-1 block text-sm font-medium"
        >
          Workspace Root Path
        </label>
        <Input
          id="workspace-root"
          type="text"
          value={draft.workspace_root}
          onChange={(e) =>
            setDraft({ ...draft, workspace_root: e.target.value })
          }
        />
        <p className="mt-1 text-xs text-muted-foreground">
          Absolute path on the host where this workspace lives.
        </p>
      </div>

      <div>
        <label
          htmlFor="default-branch"
          className="mb-1 block text-sm font-medium"
        >
          Default Branch
        </label>
        <Input
          id="default-branch"
          type="text"
          value={draft.default_branch}
          onChange={(e) =>
            setDraft({ ...draft, default_branch: e.target.value })
          }
        />
      </div>

      <div>
        <label
          htmlFor="auto-detect"
          className="flex items-center gap-2 text-sm font-medium"
        >
          <Checkbox
            id="auto-detect"
            checked={draft.auto_detect_tech_stack}
            onCheckedChange={(checked) =>
              setDraft({
                ...draft,
                auto_detect_tech_stack: checked === true,
              })
            }
          />
          Tech-Stack Auto-Detection
        </label>
        <p className="ml-6 mt-1 text-xs text-muted-foreground">
          When on, CodeFRAME infers the tech stack from project files.
        </p>
      </div>

      <div>
        <label
          htmlFor="tech-override"
          className="mb-1 block text-sm font-medium"
        >
          Manual Tech-Stack Override
        </label>
        <Input
          id="tech-override"
          type="text"
          placeholder="e.g. Python with uv, FastAPI, pytest"
          value={draft.tech_stack_override ?? ''}
          disabled={draft.auto_detect_tech_stack}
          onChange={(e) =>
            setDraft({
              ...draft,
              tech_stack_override: e.target.value || null,
            })
          }
        />
        <p className="mt-1 text-xs text-muted-foreground">
          Disabled while auto-detection is on.
        </p>
      </div>

      <div className="flex justify-end gap-2 border-t pt-4">
        <Button
          type="button"
          variant="outline"
          onClick={handleDiscard}
          disabled={!dirty || saving}
        >
          Discard
        </Button>
        <Button type="button" onClick={handleSave} disabled={!canSave}>
          {saving ? 'Saving…' : 'Save changes'}
        </Button>
      </div>
    </div>
  );
}
