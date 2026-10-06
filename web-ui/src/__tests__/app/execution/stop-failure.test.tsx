/**
 * A confirmed Stop that fails must say so (#1297). handleStop logged every
 * failure except "already finished" to the console, so on a 403 (hosted
 * mode), a 500 or a network error the user confirmed Stop, nothing visible
 * happened, and the agent kept running.
 */
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { toast } from 'sonner';
import ExecutionPage from '@/app/execution/[taskId]/page';
import { tasksApi } from '@/lib/api';

jest.mock('sonner', () => ({ toast: { success: jest.fn(), error: jest.fn() } }));
jest.mock('next/navigation', () => ({
  useParams: () => ({ taskId: 'task-1' }),
  useRouter: () => ({ push: jest.fn(), replace: jest.fn() }),
}));
jest.mock('@/lib/workspace-storage', () => ({ getSelectedWorkspacePath: () => '/ws' }));
jest.mock('@/lib/api', () => ({
  tasksApi: { getOne: jest.fn(() => new Promise(() => {})), stopExecution: jest.fn() },
  gatesApi: { run: jest.fn() },
}));
jest.mock('@/hooks/useExecutionMonitor', () => ({
  useExecutionMonitor: () => ({
    agentState: 'EXECUTING',
    sseStatus: 'open',
    isCompleted: false,
    completionStatus: null,
    currentStep: 0,
    totalSteps: 0,
    events: [],
    changedFiles: [],
  }),
}));
jest.mock('@/components/execution/ExecutionHeader', () => ({
  ExecutionHeader: ({ onStop }: { onStop: () => void }) => <button onClick={onStop}>Stop</button>,
}));
jest.mock('@/components/execution/ProgressIndicator', () => ({ ProgressIndicator: () => null }));
jest.mock('@/components/execution/EventStream', () => ({ EventStream: () => null }));
jest.mock('@/components/execution/ChangesSidebar', () => ({ ChangesSidebar: () => null }));

const stop = tasksApi.stopExecution as jest.Mock;

beforeEach(() => jest.clearAllMocks());

it('tells the user when Stop fails, so they know the agent is still running', async () => {
  stop.mockRejectedValueOnce({ detail: 'Execution is disabled in hosted mode', status_code: 403 });
  render(<ExecutionPage />);

  fireEvent.click(await screen.findByRole('button', { name: 'Stop' }));

  await waitFor(() =>
    expect(toast.error).toHaveBeenCalledWith(expect.stringContaining('Execution is disabled in hosted mode'))
  );
});

it('stays quiet when the run had already finished', async () => {
  stop.mockRejectedValueOnce({ detail: 'Run not found', status_code: 404 });
  render(<ExecutionPage />);

  fireEvent.click(await screen.findByRole('button', { name: 'Stop' }));

  await waitFor(() => expect(stop).toHaveBeenCalled());
  expect(toast.error).not.toHaveBeenCalled();
});
