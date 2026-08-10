/**
 * BatchExecutionMonitor behavioural coverage (issue #964).
 *
 * 314 LOC and the only existing test reference mocked it to null, so nothing
 * asserted that the Build surface renders batch state, offers the right
 * controls, or stops offering them once a batch is terminal. #652 recently
 * changed this component's dispatch responsibilities with no test to notice.
 */
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BatchExecutionMonitor } from '@/components/execution/BatchExecutionMonitor';

const push = jest.fn();
jest.mock('next/navigation', () => ({
  useRouter: () => ({ push }),
}));

jest.mock('@/lib/api', () => ({
  batchesApi: { get: jest.fn(), stop: jest.fn(), cancel: jest.fn() },
  tasksApi: { getOne: jest.fn() },
}));

// The expanded row opens an SSE stream; keep it inert and assert on the rows.
jest.mock('@/hooks/useExecutionMonitor', () => ({
  useExecutionMonitor: () => ({ events: [] }),
}));
jest.mock('@/components/execution/EventStream', () => ({
  EventStream: () => <div data-testid="event-stream" />,
}));

import { batchesApi, tasksApi } from '@/lib/api';

const mockGet = batchesApi.get as jest.Mock;
const mockStop = batchesApi.stop as jest.Mock;
const mockCancel = batchesApi.cancel as jest.Mock;
const mockGetOne = tasksApi.getOne as jest.Mock;

function batch(overrides: Record<string, unknown> = {}) {
  return {
    id: 'b-1',
    workspace_id: 'ws',
    task_ids: ['t-1', 't-2'],
    status: 'RUNNING',
    strategy: 'serial',
    results: { 't-1': 'COMPLETED', 't-2': 'IN_PROGRESS' },
    ...overrides,
  };
}

beforeEach(() => {
  jest.clearAllMocks();
  mockGet.mockResolvedValue(batch());
  mockGetOne.mockImplementation((_ws: string, id: string) =>
    Promise.resolve({ id, title: `Task ${id}` })
  );
});

async function renderMonitor() {
  render(<BatchExecutionMonitor batchId="b-1" workspacePath="/ws" />);
  await waitFor(() => expect(screen.getByText(/batch execution/i)).toBeInTheDocument());
}

describe('BatchExecutionMonitor — batch state', () => {
  it('shows the task count, strategy and completion progress', async () => {
    await renderMonitor();
    expect(screen.getByText(/batch execution \(2 tasks\)/i)).toBeInTheDocument();
    expect(screen.getByText(/strategy: serial/i)).toBeInTheDocument();
    // COMPLETED counts toward progress; IN_PROGRESS does not.
    expect(screen.getByText(/1\/2 complete/i)).toBeInTheDocument();
  });

  it('counts DONE as complete alongside COMPLETED', async () => {
    mockGet.mockResolvedValue(
      batch({ results: { 't-1': 'DONE', 't-2': 'COMPLETED' }, status: 'COMPLETED' })
    );
    await renderMonitor();
    expect(screen.getByText(/2\/2 complete/i)).toBeInTheDocument();
  });

  it('renders a per-task row labelled with its status', async () => {
    await renderMonitor();
    await waitFor(() => expect(screen.getByText('Task t-1')).toBeInTheDocument());
    expect(screen.getByText('Task t-2')).toBeInTheDocument();
    expect(screen.getByText('Completed')).toBeInTheDocument();
    expect(screen.getByText('Running')).toBeInTheDocument();
  });

  it('falls back to the task id before its title has loaded', async () => {
    mockGetOne.mockReturnValue(new Promise(() => {})); // never resolves
    await renderMonitor();
    expect(screen.getByText('t-1')).toBeInTheDocument();
  });

  it('treats a task with no recorded result as waiting', async () => {
    mockGet.mockResolvedValue(batch({ results: {} }));
    await renderMonitor();
    expect(screen.getAllByText('Waiting')).toHaveLength(2);
  });

  it('labels a blocked task', async () => {
    mockGet.mockResolvedValue(
      batch({ results: { 't-1': 'BLOCKED', 't-2': 'READY' } })
    );
    await renderMonitor();
    expect(screen.getByText('Blocked')).toBeInTheDocument();
  });

  it('surfaces a load failure instead of rendering an empty shell', async () => {
    mockGet.mockRejectedValue(new Error('boom'));
    render(<BatchExecutionMonitor batchId="b-1" workspacePath="/ws" />);
    await waitFor(() =>
      expect(screen.getByText(/failed to load batch details/i)).toBeInTheDocument()
    );
    expect(screen.queryByText(/batch execution/i)).not.toBeInTheDocument();
  });
});

describe('BatchExecutionMonitor — controls by batch state', () => {
  it('offers stop and cancel while the batch is active', async () => {
    await renderMonitor();
    expect(screen.getByRole('button', { name: /stop batch/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /cancel batch/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /back to tasks/i })).not.toBeInTheDocument();
  });

  it.each(['COMPLETED', 'FAILED', 'CANCELLED'])(
    'replaces the controls with a way out once %s',
    async (status) => {
      mockGet.mockResolvedValue(batch({ status }));
      await renderMonitor();
      expect(screen.queryByRole('button', { name: /stop batch/i })).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /cancel batch/i })).not.toBeInTheDocument();
      expect(screen.getByRole('button', { name: /back to tasks/i })).toBeInTheDocument();
    }
  );

  it('navigates back to the task board', async () => {
    mockGet.mockResolvedValue(batch({ status: 'COMPLETED' }));
    await renderMonitor();
    await userEvent.click(screen.getByRole('button', { name: /back to tasks/i }));
    expect(push).toHaveBeenCalledWith('/tasks');
  });
});

describe('BatchExecutionMonitor — cancel and stop', () => {
  it('confirms before cancelling, then calls the API and refetches', async () => {
    mockCancel.mockResolvedValue(batch({ status: 'CANCELLED' }));
    await renderMonitor();
    const callsBefore = mockGet.mock.calls.length;

    await userEvent.click(screen.getByRole('button', { name: /cancel batch/i }));
    const dialog = await screen.findByRole('alertdialog');
    expect(within(dialog).getByText(/cancel the entire batch/i)).toBeInTheDocument();

    await userEvent.click(within(dialog).getByRole('button', { name: /^cancel batch$/i }));

    await waitFor(() => expect(mockCancel).toHaveBeenCalledWith('/ws', 'b-1'));
    // The view must reflect the new state, not the stale one.
    await waitFor(() => expect(mockGet.mock.calls.length).toBeGreaterThan(callsBefore));
  });

  it('does not cancel when the confirmation is dismissed', async () => {
    await renderMonitor();
    await userEvent.click(screen.getByRole('button', { name: /cancel batch/i }));
    const dialog = await screen.findByRole('alertdialog');

    await userEvent.click(within(dialog).getByRole('button', { name: /keep running/i }));

    await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument());
    expect(mockCancel).not.toHaveBeenCalled();
  });

  it('confirms before stopping, then calls the API', async () => {
    mockStop.mockResolvedValue(batch({ status: 'CANCELLED' }));
    await renderMonitor();

    await userEvent.click(screen.getByRole('button', { name: /stop batch/i }));
    const dialog = await screen.findByRole('alertdialog');
    await userEvent.click(within(dialog).getByRole('button', { name: /^stop batch$/i }));

    await waitFor(() => expect(mockStop).toHaveBeenCalledWith('/ws', 'b-1'));
  });

  it('reports a failed cancel rather than looking like it worked', async () => {
    mockCancel.mockRejectedValue(new Error('nope'));
    await renderMonitor();

    await userEvent.click(screen.getByRole('button', { name: /cancel batch/i }));
    const dialog = await screen.findByRole('alertdialog');
    await userEvent.click(within(dialog).getByRole('button', { name: /^cancel batch$/i }));

    await waitFor(() =>
      expect(screen.getByText(/failed to cancel batch/i)).toBeInTheDocument()
    );
  });
});

describe('BatchExecutionMonitor — task rows', () => {
  it('auto-expands the running task', async () => {
    await renderMonitor();
    await waitFor(() => {
      const rows = screen.getAllByRole('button', { expanded: true });
      expect(rows).toHaveLength(1);
    });
    // t-2 is the IN_PROGRESS one.
    expect(
      screen.getByRole('button', { expanded: true })
    ).toHaveTextContent('Task t-2');
  });

  it('streams events only for the expanded running task', async () => {
    await renderMonitor();
    await waitFor(() => expect(screen.getByTestId('event-stream')).toBeInTheDocument());
    expect(screen.getAllByTestId('event-stream')).toHaveLength(1);
  });

  it('explains a finished task instead of streaming it', async () => {
    mockGet.mockResolvedValue(
      batch({ status: 'COMPLETED', results: { 't-1': 'COMPLETED', 't-2': 'FAILED' } })
    );
    await renderMonitor();

    await userEvent.click(await screen.findByText('Task t-1'));
    await waitFor(() =>
      expect(screen.getByText(/task completed successfully/i)).toBeInTheDocument()
    );
    expect(screen.queryByTestId('event-stream')).not.toBeInTheDocument();
  });

  it('points a failed task at diagnostics', async () => {
    mockGet.mockResolvedValue(
      batch({ status: 'FAILED', results: { 't-1': 'FAILED', 't-2': 'FAILED' } })
    );
    await renderMonitor();

    await userEvent.click(await screen.findByText('Task t-1'));
    await waitFor(() =>
      expect(screen.getByText(/check diagnostics for details/i)).toBeInTheDocument()
    );
  });

  it('collapses a row when toggled again', async () => {
    mockGet.mockResolvedValue(
      batch({ status: 'COMPLETED', results: { 't-1': 'COMPLETED', 't-2': 'COMPLETED' } })
    );
    await renderMonitor();

    const row = await screen.findByText('Task t-1');
    await userEvent.click(row);
    await waitFor(() =>
      expect(screen.getByText(/task completed successfully/i)).toBeInTheDocument()
    );

    await userEvent.click(row);
    await waitFor(() =>
      expect(screen.queryByText(/task completed successfully/i)).not.toBeInTheDocument()
    );
  });

  it('fetches each task title exactly once across refetches', async () => {
    await renderMonitor();
    await waitFor(() => expect(mockGetOne).toHaveBeenCalledTimes(2));

    // A second poll must not refetch titles it already has.
    mockGet.mockResolvedValue(batch());
    await waitFor(() => expect(mockGetOne).toHaveBeenCalledTimes(2));
  });
});
