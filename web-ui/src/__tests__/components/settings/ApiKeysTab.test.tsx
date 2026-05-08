import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import useSWR from 'swr';
import { toast } from 'sonner';

import { ApiKeysTab } from '@/components/settings/ApiKeysTab';
import { settingsApi } from '@/lib/api';
import type { KeyStatusResponse } from '@/types';

jest.mock('swr');
jest.mock('@/lib/api', () => ({
  settingsApi: {
    getKeys: jest.fn(),
    storeKey: jest.fn(),
    removeKey: jest.fn(),
    verifyKey: jest.fn(),
  },
}));
jest.mock('sonner', () => ({
  toast: {
    success: jest.fn(),
    info: jest.fn(),
    error: jest.fn(),
  },
}));

const mockUseSWR = useSWR as jest.MockedFunction<typeof useSWR>;
const mockStore = settingsApi.storeKey as jest.MockedFunction<typeof settingsApi.storeKey>;
const mockRemove = settingsApi.removeKey as jest.MockedFunction<typeof settingsApi.removeKey>;
const mockVerify = settingsApi.verifyKey as jest.MockedFunction<typeof settingsApi.verifyKey>;

function mockSWR(data: KeyStatusResponse[] | undefined, mutate = jest.fn()) {
  mockUseSWR.mockReturnValue({
    data,
    error: undefined,
    isLoading: data === undefined,
    mutate,
  } as unknown as ReturnType<typeof useSWR>);
  return mutate;
}

const NONE_STATUS: KeyStatusResponse[] = [
  { provider: 'LLM_ANTHROPIC', stored: false, source: 'none', last_four: null },
  { provider: 'LLM_OPENAI', stored: false, source: 'none', last_four: null },
  { provider: 'GIT_GITHUB', stored: false, source: 'none', last_four: null },
];

describe('ApiKeysTab', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders three key slots when no keys are stored', () => {
    mockSWR(NONE_STATUS);
    render(<ApiKeysTab />);
    expect(screen.getByText('Anthropic API Key')).toBeInTheDocument();
    expect(screen.getByText('OpenAI API Key')).toBeInTheDocument();
    expect(screen.getByText('GitHub Personal Access Token')).toBeInTheDocument();
  });

  it('shows loading state while data is undefined', () => {
    mockSWR(undefined);
    render(<ApiKeysTab />);
    expect(screen.getByText(/Loading/i)).toBeInTheDocument();
  });

  it('shows error state when load fails', () => {
    mockUseSWR.mockReturnValue({
      data: undefined,
      error: new Error('boom'),
      isLoading: false,
      mutate: jest.fn(),
    } as unknown as ReturnType<typeof useSWR>);
    render(<ApiKeysTab />);
    expect(screen.getByText(/Failed to load API key status/i)).toBeInTheDocument();
  });

  it('shows last 4 of stored key without exposing plaintext', () => {
    const stored: KeyStatusResponse[] = [
      { provider: 'LLM_ANTHROPIC', stored: true, source: 'stored', last_four: 'aaaa' },
      { provider: 'LLM_OPENAI', stored: false, source: 'none', last_four: null },
      { provider: 'GIT_GITHUB', stored: false, source: 'none', last_four: null },
    ];
    mockSWR(stored);
    render(<ApiKeysTab />);

    const anthropicInput = screen.getByLabelText(/Anthropic API Key/i);
    expect(anthropicInput).toHaveAttribute('type', 'password');
    expect((anthropicInput as HTMLInputElement).placeholder).toContain('aaaa');
    // Plaintext value should never appear in the DOM.
    expect(screen.queryByText(/sk-ant-/i)).not.toBeInTheDocument();
  });

  it('saves a key and refreshes status', async () => {
    const mutate = mockSWR(NONE_STATUS);
    mockStore.mockResolvedValue({
      provider: 'LLM_ANTHROPIC',
      stored: true,
      source: 'stored',
      last_four: '1234',
    });

    render(<ApiKeysTab />);
    const input = screen.getByLabelText(/Anthropic API Key/i);
    fireEvent.change(input, { target: { value: 'sk-ant-test-key-1234567890123456' } });

    const saveButtons = screen.getAllByRole('button', { name: /Save/i });
    await act(async () => {
      fireEvent.click(saveButtons[0]);
    });

    expect(mockStore).toHaveBeenCalledWith(
      'LLM_ANTHROPIC',
      'sk-ant-test-key-1234567890123456'
    );
    expect(toast.success).toHaveBeenCalledWith(
      expect.stringContaining('Anthropic')
    );
    expect(mutate).toHaveBeenCalled();
  });

  it('verifies a key and surfaces the result', async () => {
    mockSWR(NONE_STATUS);
    mockVerify.mockResolvedValue({
      provider: 'LLM_OPENAI',
      valid: true,
      message: 'OpenAI key accepted',
    });

    render(<ApiKeysTab />);
    const input = screen.getByLabelText(/OpenAI API Key/i);
    fireEvent.change(input, { target: { value: 'sk-proj-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx' } });

    // Find the Verify button on the OpenAI slot
    const slot = screen.getByText('OpenAI API Key').closest('[data-provider="LLM_OPENAI"]');
    expect(slot).not.toBeNull();
    const verifyButton = slot!.querySelector('button')!;
    expect(verifyButton).toHaveTextContent(/Verify/);

    await act(async () => {
      fireEvent.click(verifyButton);
    });

    await waitFor(() => {
      expect(mockVerify).toHaveBeenCalledWith(
        'LLM_OPENAI',
        'sk-proj-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'
      );
    });
    expect(screen.getByText(/Valid/)).toBeInTheDocument();
  });

  it('reports invalid verification with a toast and inline message', async () => {
    mockSWR(NONE_STATUS);
    mockVerify.mockResolvedValue({
      provider: 'GIT_GITHUB',
      valid: false,
      message: '401 Unauthorized: invalid GitHub token',
    });

    render(<ApiKeysTab />);
    const input = screen.getByLabelText(/GitHub Personal Access Token/i);
    fireEvent.change(input, { target: { value: 'ghp_invalidtoken_xxxxxxxxxxxxxxxxxxxxxx' } });

    const slot = screen.getByText('GitHub Personal Access Token').closest('[data-provider="GIT_GITHUB"]');
    const verifyButton = slot!.querySelector('button')!;

    await act(async () => {
      fireEvent.click(verifyButton);
    });

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith(
        expect.stringContaining('401')
      );
    });
    expect(screen.getByText(/Invalid/)).toBeInTheDocument();
  });

  it('removes a stored key and refreshes status', async () => {
    const stored: KeyStatusResponse[] = [
      { provider: 'LLM_ANTHROPIC', stored: true, source: 'stored', last_four: 'aaaa' },
      { provider: 'LLM_OPENAI', stored: false, source: 'none', last_four: null },
      { provider: 'GIT_GITHUB', stored: false, source: 'none', last_four: null },
    ];
    const mutate = mockSWR(stored);
    mockRemove.mockResolvedValue(undefined);

    render(<ApiKeysTab />);
    const removeButton = screen.getByRole('button', { name: /Remove/i });
    await act(async () => {
      fireEvent.click(removeButton);
    });

    expect(mockRemove).toHaveBeenCalledWith('LLM_ANTHROPIC');
    expect(toast.success).toHaveBeenCalledWith(expect.stringContaining('removed'));
    expect(mutate).toHaveBeenCalled();
  });

  it('disables save and remove for env-source keys', () => {
    const stored: KeyStatusResponse[] = [
      { provider: 'LLM_ANTHROPIC', stored: true, source: 'environment', last_four: '5678' },
      { provider: 'LLM_OPENAI', stored: false, source: 'none', last_four: null },
      { provider: 'GIT_GITHUB', stored: false, source: 'none', last_four: null },
    ];
    mockSWR(stored);
    render(<ApiKeysTab />);

    const slot = screen.getByText('Anthropic API Key').closest('[data-provider="LLM_ANTHROPIC"]')!;
    const input = slot.querySelector('input')!;
    expect(input).toBeDisabled();
    expect(screen.getByText(/Loaded from environment variable/i)).toBeInTheDocument();
    // No remove button rendered for environment-source.
    expect(slot.querySelector('button[aria-label]')).toBeNull();
  });
});
