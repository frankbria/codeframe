import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import useSWR from 'swr';
import { toast } from 'sonner';

import SettingsPage from '@/app/settings/page';
import { settingsApi } from '@/lib/api';
import * as storage from '@/lib/workspace-storage';
import type { AgentSettings } from '@/types';

// ── Mocks ────────────────────────────────────────────────────────────────

jest.mock('swr');
jest.mock('@/lib/workspace-storage', () => ({
  getSelectedWorkspacePath: jest.fn(),
}));
jest.mock('@/lib/api', () => ({
  settingsApi: {
    get: jest.fn(),
    update: jest.fn(),
  },
}));
jest.mock('sonner', () => ({
  toast: {
    success: jest.fn(),
    info: jest.fn(),
    error: jest.fn(),
  },
}));
jest.mock('next/link', () => {
  const MockLink = ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  );
  MockLink.displayName = 'MockLink';
  return MockLink;
});

const mockUseSWR = useSWR as jest.MockedFunction<typeof useSWR>;
const mockGetWorkspace = storage.getSelectedWorkspacePath as jest.MockedFunction<
  typeof storage.getSelectedWorkspacePath
>;
const mockUpdate = settingsApi.update as jest.MockedFunction<typeof settingsApi.update>;

// ── Helpers ──────────────────────────────────────────────────────────────

const WORKSPACE = '/home/user/project';

const SAMPLE_SETTINGS: AgentSettings = {
  agent_models: [
    { agent_type: 'claude_code', default_model: 'claude-opus-4' },
    { agent_type: 'codex', default_model: '' },
    { agent_type: 'opencode', default_model: '' },
    { agent_type: 'react', default_model: '' },
  ],
  max_turns: 25,
  max_cost_usd: 5.0,
};

function mockSWR(data: AgentSettings | undefined, mutate = jest.fn()) {
  mockUseSWR.mockReturnValue({
    data,
    error: undefined,
    isLoading: data === undefined,
    mutate,
  } as unknown as ReturnType<typeof useSWR>);
  return mutate;
}

// ── Tests ────────────────────────────────────────────────────────────────

describe('SettingsPage', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('without workspace', () => {
    it('shows workspace prompt when no workspace selected', () => {
      mockGetWorkspace.mockReturnValue(null);
      mockSWR(undefined);
      render(<SettingsPage />);
      expect(screen.getByText(/No workspace selected/i)).toBeInTheDocument();
    });
  });

  describe('with workspace', () => {
    beforeEach(() => {
      mockGetWorkspace.mockReturnValue(WORKSPACE);
    });

    it('renders all four tabs', () => {
      mockSWR(SAMPLE_SETTINGS);
      render(<SettingsPage />);
      expect(screen.getByRole('tab', { name: 'Agent' })).toBeInTheDocument();
      expect(screen.getByRole('tab', { name: 'API Keys' })).toBeInTheDocument();
      expect(screen.getByRole('tab', { name: 'PROOF9' })).toBeInTheDocument();
      expect(screen.getByRole('tab', { name: 'Workspace' })).toBeInTheDocument();
    });

    it('loads settings into form on mount', async () => {
      mockSWR(SAMPLE_SETTINGS);
      render(<SettingsPage />);

      await waitFor(() => {
        expect(screen.getByLabelText(/Max turns per task/i)).toHaveValue(25);
      });
      expect(screen.getByLabelText(/Max cost per task/i)).toHaveValue(5);
    });

    it('saves edited settings via the API', async () => {
      const mutate = mockSWR(SAMPLE_SETTINGS);
      mockUpdate.mockResolvedValue({ ...SAMPLE_SETTINGS, max_turns: 30 });

      render(<SettingsPage />);

      const maxTurnsInput = await screen.findByLabelText(/Max turns per task/i);
      fireEvent.change(maxTurnsInput, { target: { value: '30' } });

      const saveButton = screen.getByRole('button', { name: /Save/i });
      await act(async () => {
        fireEvent.click(saveButton);
      });

      expect(mockUpdate).toHaveBeenCalledWith(
        WORKSPACE,
        expect.objectContaining({ max_turns: 30 })
      );
      expect(toast.success).toHaveBeenCalledWith('Settings saved');
      expect(mutate).toHaveBeenCalled();
    });

    it('discards changes back to last loaded data', async () => {
      mockSWR(SAMPLE_SETTINGS);
      render(<SettingsPage />);

      const maxTurnsInput = await screen.findByLabelText(/Max turns per task/i);
      fireEvent.change(maxTurnsInput, { target: { value: '99' } });
      expect(maxTurnsInput).toHaveValue(99);

      const discardButton = screen.getByRole('button', { name: /Discard/i });
      fireEvent.click(discardButton);

      await waitFor(() => {
        expect(maxTurnsInput).toHaveValue(25);
      });
      expect(toast.info).toHaveBeenCalledWith('Changes discarded');
    });

    it('exposes triggers for the three stub tabs', () => {
      mockSWR(SAMPLE_SETTINGS);
      render(<SettingsPage />);

      // Stub tabs are present even though their panels mount lazily in radix.
      ['API Keys', 'PROOF9', 'Workspace'].forEach((name) => {
        expect(screen.getByRole('tab', { name })).toBeInTheDocument();
      });
    });

    it('shows error message when SWR errors', () => {
      mockUseSWR.mockReturnValue({
        data: undefined,
        error: new Error('boom'),
        isLoading: false,
        mutate: jest.fn(),
      } as unknown as ReturnType<typeof useSWR>);
      render(<SettingsPage />);
      expect(screen.getByText(/Failed to load settings/i)).toBeInTheDocument();
    });
  });
});
