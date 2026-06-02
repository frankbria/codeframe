import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import useSWR from 'swr';

import { GitHubIntegrationCard } from '@/components/settings/GitHubIntegrationCard';
import { integrationsApi } from '@/lib/api';
import type { GitHubIntegrationStatus } from '@/types';

jest.mock('swr');
jest.mock('@/lib/api', () => ({
  integrationsApi: {
    getStatus: jest.fn(),
    connect: jest.fn(),
    disconnect: jest.fn(),
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
const mockConnect = integrationsApi.connect as jest.MockedFunction<
  typeof integrationsApi.connect
>;
const mockDisconnect = integrationsApi.disconnect as jest.MockedFunction<
  typeof integrationsApi.disconnect
>;

const DISCONNECTED: GitHubIntegrationStatus = {
  connected: false,
  repo: null,
  owner_login: null,
  owner_avatar_url: null,
};

const CONNECTED: GitHubIntegrationStatus = {
  connected: true,
  repo: 'acme/app',
  owner_login: 'acme',
  owner_avatar_url: 'https://avatars/1',
};

function mockSWR(
  data: GitHubIntegrationStatus | undefined,
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

describe('GitHubIntegrationCard', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('shows a no-workspace message when path is null', () => {
    mockSWR(undefined);
    render(<GitHubIntegrationCard workspacePath={null} />);
    expect(screen.getByText(/select a workspace/i)).toBeInTheDocument();
  });

  it('renders PAT + repo inputs and Connect when disconnected', () => {
    mockSWR(DISCONNECTED);
    render(<GitHubIntegrationCard workspacePath="/ws" />);
    expect(screen.getByLabelText(/personal access token/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/repository/i)).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /^connect$/i })
    ).toBeInTheDocument();
  });

  it('PAT field is a password input', () => {
    mockSWR(DISCONNECTED);
    render(<GitHubIntegrationCard workspacePath="/ws" />);
    const pat = screen.getByLabelText(/personal access token/i);
    expect(pat).toHaveAttribute('type', 'password');
  });

  it('Connect disabled until both fields filled', () => {
    mockSWR(DISCONNECTED);
    render(<GitHubIntegrationCard workspacePath="/ws" />);
    const connectBtn = screen.getByRole('button', { name: /^connect$/i });
    expect(connectBtn).toBeDisabled();

    fireEvent.change(screen.getByLabelText(/personal access token/i), {
      target: { value: 'ghp_token' },
    });
    expect(connectBtn).toBeDisabled();

    fireEvent.change(screen.getByLabelText(/repository/i), {
      target: { value: 'acme/app' },
    });
    expect(connectBtn).toBeEnabled();
  });

  it('calls connect and switches to connected on success', async () => {
    const mutate = mockSWR(DISCONNECTED);
    mockConnect.mockResolvedValueOnce({
      connected: true,
      repo: 'acme/app',
      owner_login: 'acme',
      owner_avatar_url: 'https://avatars/1',
    });

    render(<GitHubIntegrationCard workspacePath="/ws" />);

    fireEvent.change(screen.getByLabelText(/personal access token/i), {
      target: { value: 'ghp_token' },
    });
    fireEvent.change(screen.getByLabelText(/repository/i), {
      target: { value: 'acme/app' },
    });

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /^connect$/i }));
    });

    expect(mockConnect).toHaveBeenCalledWith('/ws', 'ghp_token', 'acme/app');
    expect(mutate).toHaveBeenCalledWith(
      expect.objectContaining({ connected: true, repo: 'acme/app' }),
      { revalidate: false }
    );
    expect(toast.success).toHaveBeenCalled();
  });

  it('shows a clear error message when connect fails', async () => {
    mockSWR(DISCONNECTED);
    mockConnect.mockRejectedValueOnce({ detail: 'Invalid GitHub token.' });

    render(<GitHubIntegrationCard workspacePath="/ws" />);

    fireEvent.change(screen.getByLabelText(/personal access token/i), {
      target: { value: 'ghp_bad' },
    });
    fireEvent.change(screen.getByLabelText(/repository/i), {
      target: { value: 'acme/app' },
    });

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /^connect$/i }));
    });

    await waitFor(() => {
      expect(screen.getByText(/invalid github token/i)).toBeInTheDocument();
    });
  });

  it('renders connected state with repo and Disconnect', () => {
    mockSWR(CONNECTED);
    render(<GitHubIntegrationCard workspacePath="/ws" />);
    expect(screen.getByText('acme/app')).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /disconnect/i })
    ).toBeInTheDocument();
  });

  it('calls disconnect and reverts to disconnected', async () => {
    const mutate = mockSWR(CONNECTED);
    mockDisconnect.mockResolvedValueOnce(undefined);

    render(<GitHubIntegrationCard workspacePath="/ws" />);

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /disconnect/i }));
    });

    expect(mockDisconnect).toHaveBeenCalledWith('/ws');
    expect(mutate).toHaveBeenCalledWith(
      expect.objectContaining({ connected: false, repo: null }),
      { revalidate: false }
    );
    expect(toast.success).toHaveBeenCalled();
  });
});
