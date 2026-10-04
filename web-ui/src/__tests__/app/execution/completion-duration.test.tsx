/**
 * The completion banner shows a duration only when one is known (#1306). The
 * agent emitted duration_seconds=0, so every run read "complete in 0s".
 */
import { render, screen } from '@testing-library/react';
import ExecutionPage from '@/app/execution/[taskId]/page';

let monitorDuration: number | null = null;

jest.mock('sonner', () => ({ toast: { success: jest.fn(), error: jest.fn() } }));
jest.mock('next/navigation', () => ({
  useParams: () => ({ taskId: 'task-1' }),
  useRouter: () => ({ push: jest.fn(), replace: jest.fn() }),
}));
jest.mock('@/lib/workspace-storage', () => ({ getSelectedWorkspacePath: () => '/ws' }));
jest.mock('@/lib/api', () => ({
  tasksApi: { getOne: jest.fn(() => new Promise(() => {})), stopExecution: jest.fn() },
  gatesApi: { run: jest.fn(() => new Promise(() => {})) },
}));
jest.mock('@/hooks/useExecutionMonitor', () => ({
  useExecutionMonitor: () => ({
    agentState: 'COMPLETED',
    sseStatus: 'closed',
    isCompleted: true,
    completionStatus: 'completed',
    duration: monitorDuration,
    currentStep: 0,
    totalSteps: 0,
    events: [],
    changedFiles: [],
  }),
}));
jest.mock('@/components/execution/ExecutionHeader', () => ({ ExecutionHeader: () => null }));
jest.mock('@/components/execution/ProgressIndicator', () => ({ ProgressIndicator: () => null }));
jest.mock('@/components/execution/EventStream', () => ({ EventStream: () => null }));
jest.mock('@/components/execution/ChangesSidebar', () => ({ ChangesSidebar: () => null }));

it('shows the run time when it is known', async () => {
  monitorDuration = 42.4;
  render(<ExecutionPage />);
  expect(await screen.findByText(/Execution complete in 42s\./)).toBeInTheDocument();
});

it('treats a zero duration as unknown rather than "0s"', async () => {
  monitorDuration = 0;
  render(<ExecutionPage />);
  const banner = await screen.findByText(/Execution complete/);
  expect(banner.textContent).not.toMatch(/0s/);
  expect(banner.textContent).toMatch(/^Execution complete\./);
});
