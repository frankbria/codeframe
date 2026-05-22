import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import useSWR from 'swr';

import { NotificationsTab } from '@/components/settings/NotificationsTab';
import { notificationsApi } from '@/lib/api';
import type {
  NotificationSettingsResponse,
  TestWebhookResponse,
} from '@/types';

jest.mock('swr');
jest.mock('@/lib/api', () => ({
  notificationsApi: {
    get: jest.fn(),
    update: jest.fn(),
    test: jest.fn(),
  },
}));
jest.mock('sonner', () => ({
  toast: {
    success: jest.fn(),
    info: jest.fn(),
    error: jest.fn(),
  },
}));

import { toast } from 'sonner';

const mockUseSWR = useSWR as jest.MockedFunction<typeof useSWR>;
const mockUpdate = notificationsApi.update as jest.MockedFunction<
  typeof notificationsApi.update
>;
const mockTest = notificationsApi.test as jest.MockedFunction<
  typeof notificationsApi.test
>;

const DEFAULT_CONFIG: NotificationSettingsResponse = {
  webhook_url: null,
  webhook_enabled: false,
};

const CONFIGURED: NotificationSettingsResponse = {
  webhook_url: 'https://hooks.example.com/abc',
  webhook_enabled: true,
};

function mockSWR(
  data: NotificationSettingsResponse | undefined,
  mutate = jest.fn()
) {
  mockUseSWR.mockReturnValue({
    data,
    error: undefined,
    isLoading: data === undefined,
    mutate,
  } as unknown as ReturnType<typeof useSWR>);
  return mutate;
}

describe('NotificationsTab', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('shows a no-workspace message when path is null', () => {
    mockSWR(undefined);
    render(<NotificationsTab workspacePath={null} />);
    expect(
      screen.getByText(/select a workspace/i)
    ).toBeInTheDocument();
  });

  it('renders the URL input and toggle when data loaded', () => {
    mockSWR(DEFAULT_CONFIG);
    render(<NotificationsTab workspacePath="/ws" />);
    expect(screen.getByLabelText(/webhook url/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/enable webhook notifications/i)).toBeInTheDocument();
  });

  it('Test button disabled when no URL configured', () => {
    mockSWR(DEFAULT_CONFIG);
    render(<NotificationsTab workspacePath="/ws" />);
    expect(screen.getByRole('button', { name: /^test$/i })).toBeDisabled();
  });

  it('Test button disabled when the user has unsaved URL changes', () => {
    mockSWR(DEFAULT_CONFIG);
    render(<NotificationsTab workspacePath="/ws" />);
    fireEvent.change(screen.getByLabelText(/webhook url/i), {
      target: { value: 'https://new.example/h' },
    });
    expect(screen.getByRole('button', { name: /^test$/i })).toBeDisabled();
  });

  it('Test button enabled when URL is saved and not dirty', () => {
    mockSWR(CONFIGURED);
    render(<NotificationsTab workspacePath="/ws" />);
    expect(screen.getByRole('button', { name: /^test$/i })).toBeEnabled();
  });


  it('Save and Discard disabled when not dirty', () => {
    mockSWR(CONFIGURED);
    render(<NotificationsTab workspacePath="/ws" />);
    expect(screen.getByRole('button', { name: /save changes/i })).toBeDisabled();
    expect(screen.getByRole('button', { name: /discard/i })).toBeDisabled();
  });

  it('Save becomes enabled after URL change', () => {
    mockSWR(DEFAULT_CONFIG);
    render(<NotificationsTab workspacePath="/ws" />);
    fireEvent.change(screen.getByLabelText(/webhook url/i), {
      target: { value: 'https://x.test/h' },
    });
    expect(screen.getByRole('button', { name: /save changes/i })).toBeEnabled();
  });

  it('calls notificationsApi.update with trimmed URL on Save', async () => {
    const mutate = mockSWR(DEFAULT_CONFIG);
    mockUpdate.mockResolvedValueOnce({
      webhook_url: 'https://x.test/h',
      webhook_enabled: true,
    });

    render(<NotificationsTab workspacePath="/ws" />);

    fireEvent.change(screen.getByLabelText(/webhook url/i), {
      target: { value: '  https://x.test/h  ' },
    });
    fireEvent.click(screen.getByLabelText(/enable webhook notifications/i));

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /save changes/i }));
    });

    expect(mockUpdate).toHaveBeenCalledWith('/ws', {
      webhook_url: 'https://x.test/h',
      webhook_enabled: true,
    });
    expect(mutate).toHaveBeenCalled();
    expect(toast.success).toHaveBeenCalledWith('Notification settings saved');
  });

  it('shows success toast with status code when Test succeeds', async () => {
    mockSWR(CONFIGURED);
    const result: TestWebhookResponse = {
      ok: true,
      status_code: 204,
      error: null,
    };
    mockTest.mockResolvedValueOnce(result);

    render(<NotificationsTab workspacePath="/ws" />);

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /^test$/i }));
    });

    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith(
        expect.stringContaining('204')
      );
    });
  });

  it('shows error toast with status code when Test returns non-2xx', async () => {
    mockSWR(CONFIGURED);
    const result: TestWebhookResponse = {
      ok: false,
      status_code: 500,
      error: null,
    };
    mockTest.mockResolvedValueOnce(result);

    render(<NotificationsTab workspacePath="/ws" />);

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /^test$/i }));
    });

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith(
        expect.stringContaining('500')
      );
    });
  });

  it('shows error toast with message when Test has network error', async () => {
    mockSWR(CONFIGURED);
    const result: TestWebhookResponse = {
      ok: false,
      status_code: null,
      error: 'Timeout after 5s',
    };
    mockTest.mockResolvedValueOnce(result);

    render(<NotificationsTab workspacePath="/ws" />);

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /^test$/i }));
    });

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith(
        expect.stringContaining('Timeout')
      );
    });
  });

  it('Discard reverts unsaved edits', () => {
    mockSWR(CONFIGURED);
    render(<NotificationsTab workspacePath="/ws" />);

    const urlInput = screen.getByLabelText(/webhook url/i) as HTMLInputElement;
    fireEvent.change(urlInput, { target: { value: 'https://different/h' } });
    expect(urlInput.value).toBe('https://different/h');

    fireEvent.click(screen.getByRole('button', { name: /discard/i }));
    expect(urlInput.value).toBe('https://hooks.example.com/abc');
    expect(toast.info).toHaveBeenCalledWith('Changes discarded');
  });
});
