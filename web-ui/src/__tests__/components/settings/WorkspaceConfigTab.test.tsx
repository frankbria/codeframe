import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import useSWR from 'swr';

import { WorkspaceConfigTab } from '@/components/settings/WorkspaceConfigTab';
import { workspaceConfigApi } from '@/lib/api';
import type { WorkspaceConfigResponse } from '@/types';

jest.mock('swr');
jest.mock('@/lib/api', () => ({
  workspaceConfigApi: {
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
const mockUpdate = workspaceConfigApi.updateConfig as jest.MockedFunction<
  typeof workspaceConfigApi.updateConfig
>;

const DEFAULT_CONFIG: WorkspaceConfigResponse = {
  workspace_root: '/home/user/proj',
  default_branch: 'main',
  auto_detect_tech_stack: true,
  tech_stack_override: null,
};

function mockSWR(data: WorkspaceConfigResponse | undefined, mutate = jest.fn()) {
  mockUseSWR.mockReturnValue({
    data,
    error: undefined,
    isLoading: data === undefined,
    mutate,
  } as unknown as ReturnType<typeof useSWR>);
  return mutate;
}

describe('WorkspaceConfigTab', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('shows a no-workspace message when path is null', () => {
    mockSWR(undefined);
    render(<WorkspaceConfigTab workspacePath={null} />);
    expect(screen.getByText(/select a workspace/i)).toBeInTheDocument();
  });

  it('renders the four config fields when data loaded', () => {
    mockSWR(DEFAULT_CONFIG);
    render(<WorkspaceConfigTab workspacePath="/ws" />);

    expect(screen.getByLabelText(/workspace root path/i)).toHaveValue('/home/user/proj');
    expect(screen.getByLabelText(/default branch/i)).toHaveValue('main');
    expect(screen.getByLabelText(/manual tech-stack override/i)).toBeDisabled();
  });

  it('disables tech-stack override input when auto-detect is on', () => {
    mockSWR(DEFAULT_CONFIG);
    render(<WorkspaceConfigTab workspacePath="/ws" />);
    expect(screen.getByLabelText(/manual tech-stack override/i)).toBeDisabled();
  });

  it('enables tech-stack override when auto-detect is off', () => {
    mockSWR({ ...DEFAULT_CONFIG, auto_detect_tech_stack: false });
    render(<WorkspaceConfigTab workspacePath="/ws" />);
    expect(screen.getByLabelText(/manual tech-stack override/i)).toBeEnabled();
  });

  it('Save and Discard disabled when not dirty', () => {
    mockSWR(DEFAULT_CONFIG);
    render(<WorkspaceConfigTab workspacePath="/ws" />);
    expect(screen.getByRole('button', { name: /save/i })).toBeDisabled();
    expect(screen.getByRole('button', { name: /discard/i })).toBeDisabled();
  });

  it('editing default branch enables Save and persists on click', async () => {
    const mutate = mockSWR(DEFAULT_CONFIG);
    mockUpdate.mockResolvedValue({ ...DEFAULT_CONFIG, default_branch: 'develop' });

    render(<WorkspaceConfigTab workspacePath="/ws" />);
    const branchInput = screen.getByLabelText(/default branch/i);
    fireEvent.change(branchInput, { target: { value: 'develop' } });

    const saveButton = screen.getByRole('button', { name: /save/i });
    expect(saveButton).toBeEnabled();

    await act(async () => {
      fireEvent.click(saveButton);
    });
    await waitFor(() => expect(mockUpdate).toHaveBeenCalledTimes(1));
    expect(mockUpdate).toHaveBeenCalledWith(
      '/ws',
      expect.objectContaining({ default_branch: 'develop' })
    );
    expect(mutate).toHaveBeenCalled();
  });

  it('Save stays disabled when default branch is emptied', () => {
    mockSWR(DEFAULT_CONFIG);
    render(<WorkspaceConfigTab workspacePath="/ws" />);

    const branchInput = screen.getByLabelText(/default branch/i);
    fireEvent.change(branchInput, { target: { value: '' } });
    expect(screen.getByRole('button', { name: /save/i })).toBeDisabled();
  });

  it('Discard resets the form', () => {
    mockSWR(DEFAULT_CONFIG);
    render(<WorkspaceConfigTab workspacePath="/ws" />);

    const branchInput = screen.getByLabelText(/default branch/i);
    fireEvent.change(branchInput, { target: { value: 'develop' } });
    expect(branchInput).toHaveValue('develop');

    fireEvent.click(screen.getByRole('button', { name: /discard/i }));
    expect(screen.getByLabelText(/default branch/i)).toHaveValue('main');
  });
});
