import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import useSWR from 'swr';

import { Proof9DefaultsTab } from '@/components/settings/Proof9DefaultsTab';
import { proofConfigApi } from '@/lib/api';
import type { ProofConfigResponse } from '@/types';

jest.mock('swr');
jest.mock('@/lib/api', () => ({
  proofConfigApi: {
    getConfig: jest.fn(),
    updateConfig: jest.fn(),
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
const mockUpdate = proofConfigApi.updateConfig as jest.MockedFunction<
  typeof proofConfigApi.updateConfig
>;

const ALL_ENABLED_STRICT: ProofConfigResponse = {
  enabled_gates: ['unit', 'contract', 'e2e', 'visual', 'a11y', 'perf', 'sec', 'demo', 'manual'],
  strictness: 'strict',
};

function mockSWR(data: ProofConfigResponse | undefined, mutate = jest.fn()) {
  mockUseSWR.mockReturnValue({
    data,
    error: undefined,
    isLoading: data === undefined,
    mutate,
  } as unknown as ReturnType<typeof useSWR>);
  return mutate;
}

describe('Proof9DefaultsTab', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('shows a no-workspace message when path is null', () => {
    mockSWR(undefined);
    render(<Proof9DefaultsTab workspacePath={null} />);
    expect(screen.getByText(/select a workspace/i)).toBeInTheDocument();
  });

  it('renders all 9 gate checkboxes when data loaded', () => {
    mockSWR(ALL_ENABLED_STRICT);
    render(<Proof9DefaultsTab workspacePath="/ws" />);
    const checkboxes = screen.getAllByRole('checkbox');
    expect(checkboxes).toHaveLength(9);
    checkboxes.forEach((cb) => {
      expect(cb).toHaveAttribute('data-state', 'checked');
    });
  });

  it('Save and Discard are disabled when not dirty', () => {
    mockSWR(ALL_ENABLED_STRICT);
    render(<Proof9DefaultsTab workspacePath="/ws" />);
    expect(screen.getByRole('button', { name: /save/i })).toBeDisabled();
    expect(screen.getByRole('button', { name: /discard/i })).toBeDisabled();
  });

  it('toggling a checkbox enables Save', () => {
    mockSWR(ALL_ENABLED_STRICT);
    render(<Proof9DefaultsTab workspacePath="/ws" />);

    const unitCheckbox = screen.getAllByRole('checkbox')[0];
    fireEvent.click(unitCheckbox);

    expect(screen.getByRole('button', { name: /save/i })).toBeEnabled();
  });

  it('Save calls updateConfig with the current draft', async () => {
    const mutate = mockSWR(ALL_ENABLED_STRICT);
    mockUpdate.mockResolvedValue({
      enabled_gates: ['contract', 'e2e', 'visual', 'a11y', 'perf', 'sec', 'demo', 'manual'],
      strictness: 'strict',
    });

    render(<Proof9DefaultsTab workspacePath="/ws" />);
    const unitCheckbox = screen.getAllByRole('checkbox')[0];
    fireEvent.click(unitCheckbox);

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /save/i }));
    });

    await waitFor(() => {
      expect(mockUpdate).toHaveBeenCalledTimes(1);
    });
    expect(mockUpdate).toHaveBeenCalledWith('/ws', expect.objectContaining({
      strictness: 'strict',
    }));
    const callArgs = mockUpdate.mock.calls[0][1];
    expect(callArgs.enabled_gates).not.toContain('unit');
    expect(mutate).toHaveBeenCalled();
  });

  it('shows a warning banner when no gates are enabled', () => {
    mockSWR({ enabled_gates: [], strictness: 'strict' });
    render(<Proof9DefaultsTab workspacePath="/ws" />);
    expect(screen.getByRole('alert')).toHaveTextContent(/all gates disabled/i);
  });

  it('hides the banner once at least one gate is selected', () => {
    mockSWR(ALL_ENABLED_STRICT);
    render(<Proof9DefaultsTab workspacePath="/ws" />);
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('Discard resets the draft to fetched data', () => {
    mockSWR(ALL_ENABLED_STRICT);
    render(<Proof9DefaultsTab workspacePath="/ws" />);

    const unitCheckbox = screen.getAllByRole('checkbox')[0];
    fireEvent.click(unitCheckbox);
    expect(screen.getByRole('button', { name: /save/i })).toBeEnabled();

    fireEvent.click(screen.getByRole('button', { name: /discard/i }));
    expect(screen.getByRole('button', { name: /save/i })).toBeDisabled();
  });
});
