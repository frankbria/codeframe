'use client';

import { useEffect, useState } from 'react';
import useSWR from 'swr';
import { toast } from 'sonner';

import { notificationsApi } from '@/lib/api';
import type {
  ApiError,
  NotificationSettingsResponse,
} from '@/types';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';

interface NotificationsTabProps {
  workspacePath: string | null;
}

function isDirty(
  a: NotificationSettingsResponse,
  b: NotificationSettingsResponse
): boolean {
  return (
    (a.webhook_url ?? '') !== (b.webhook_url ?? '') ||
    a.webhook_enabled !== b.webhook_enabled
  );
}

export function NotificationsTab({ workspacePath }: NotificationsTabProps) {
  const swrKey = workspacePath ? ['notifications-settings', workspacePath] : null;
  const { data, error, mutate } = useSWR<NotificationSettingsResponse>(
    swrKey,
    () => notificationsApi.get(workspacePath!)
  );

  const [draft, setDraft] = useState<NotificationSettingsResponse | null>(null);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);

  useEffect(() => {
    if (data) {
      setDraft({ ...data });
    }
  }, [data]);

  if (!workspacePath) {
    return (
      <p className="text-sm text-muted-foreground">
        Select a workspace from the sidebar to manage notifications.
      </p>
    );
  }
  if (error) {
    return (
      <p className="text-sm text-destructive">
        Failed to load notification settings. Check the server logs.
      </p>
    );
  }
  if (!data || !draft) {
    return <p className="text-sm text-muted-foreground">Loading…</p>;
  }

  const trimmedUrl = (draft.webhook_url ?? '').trim();
  const dirty = isDirty(data, draft);
  const canSave = dirty && !saving;
  // Test must require BOTH a saved URL AND no pending edits — including
  // whitespace-only edits, which trim to a value that matches `data.webhook_url`
  // but still leave the persisted form mid-edit.
  const canTest = !testing && !dirty && !!data.webhook_url && trimmedUrl.length > 0;

  const handleSave = async () => {
    setSaving(true);
    try {
      const saved = await notificationsApi.update(workspacePath, {
        webhook_url: trimmedUrl || null,
        webhook_enabled: draft.webhook_enabled,
      });
      await mutate(saved, { revalidate: false });
      toast.success('Notification settings saved');
    } catch (err) {
      const apiError = err as ApiError;
      toast.error(apiError.detail || 'Failed to save notification settings');
    } finally {
      setSaving(false);
    }
  };

  const handleDiscard = () => {
    setDraft({ ...data });
    toast.info('Changes discarded');
  };

  const handleTest = async () => {
    setTesting(true);
    try {
      const result = await notificationsApi.test(workspacePath);
      if (result.ok) {
        toast.success(
          `✓ Webhook responded ${result.status_code ?? 'OK'}`
        );
      } else if (result.status_code !== null && result.status_code !== undefined) {
        toast.error(
          `✗ Webhook returned ${result.status_code}`
        );
      } else {
        toast.error(`✗ ${result.error ?? 'Webhook request failed'}`);
      }
    } catch (err) {
      const apiError = err as ApiError;
      toast.error(apiError.detail || 'Test request failed');
    } finally {
      setTesting(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <label
          htmlFor="webhook-url"
          className="mb-1 block text-sm font-medium"
        >
          Webhook URL
        </label>
        <div className="flex gap-2">
          <Input
            id="webhook-url"
            type="url"
            placeholder="https://hooks.slack.com/services/..."
            value={draft.webhook_url ?? ''}
            onChange={(e) =>
              setDraft({ ...draft, webhook_url: e.target.value || null })
            }
            className="flex-1"
          />
          <Button
            type="button"
            variant="outline"
            onClick={handleTest}
            disabled={!canTest}
            title={
              dirty
                ? 'Save the URL before testing'
                : !trimmedUrl
                  ? 'Set a URL first'
                  : 'Send a test payload'
            }
          >
            {testing ? 'Testing…' : 'Test'}
          </Button>
        </div>
        <p className="mt-1 text-xs text-muted-foreground">
          A JSON payload is POSTed to this URL on batch completion, blocker
          creation, and PR merge.
        </p>
      </div>

      <div>
        <label
          htmlFor="webhook-enabled"
          className="flex items-center gap-2 text-sm font-medium"
        >
          <Checkbox
            id="webhook-enabled"
            checked={draft.webhook_enabled}
            onCheckedChange={(checked) =>
              setDraft({ ...draft, webhook_enabled: checked === true })
            }
          />
          Enable webhook notifications
        </label>
        <p className="ml-6 mt-1 text-xs text-muted-foreground">
          Events: batch.completed, blocker.created, pr.merged. Failures are
          logged but never break the triggering operation.
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
