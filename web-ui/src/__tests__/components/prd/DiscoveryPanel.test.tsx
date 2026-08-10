/**
 * DiscoveryPanel behavioural coverage (issue #965).
 *
 * 304 LOC orchestrating the Think phase's marquee Socratic flow, at 0%
 * statement and branch coverage with no e2e mention — so a broken resume or a
 * swallowed submit error shipped green.
 *
 * These cover the four paths the issue names: start, resume, submit-answer
 * error handling, and generate-PRD.
 */
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { DiscoveryPanel } from '@/components/prd/DiscoveryPanel';

jest.mock('@/lib/api', () => ({
  discoveryApi: {
    start: jest.fn(),
    getStatus: jest.fn(),
    submitAnswer: jest.fn(),
    generatePrd: jest.fn(),
    reset: jest.fn(),
  },
  prdApi: { getLatest: jest.fn() },
}));

// Thin harnesses: the transcript and input have their own concerns; this file
// is about the orchestration between them and the API.
jest.mock('@/components/prd/DiscoveryTranscript', () => ({
  DiscoveryTranscript: ({
    messages,
    isThinking,
  }: {
    messages: { role: string; content: string }[];
    isThinking: boolean;
  }) => (
    <div>
      <span data-testid="thinking">{String(isThinking)}</span>
      <ul data-testid="transcript">
        {messages.map((m, i) => (
          <li key={i}>{`${m.role}: ${m.content}`}</li>
        ))}
      </ul>
    </div>
  ),
}));

jest.mock('@/components/prd/DiscoveryInput', () => ({
  DiscoveryInput: ({
    onSubmit,
    disabled,
  }: {
    onSubmit: (a: string) => void;
    disabled: boolean;
  }) => (
    <button disabled={disabled} onClick={() => onSubmit('my answer')}>
      submit-answer
    </button>
  ),
}));

import { discoveryApi, prdApi } from '@/lib/api';

const mockStart = discoveryApi.start as jest.Mock;
const mockStatus = discoveryApi.getStatus as jest.Mock;
const mockSubmit = discoveryApi.submitAnswer as jest.Mock;
const mockGenerate = discoveryApi.generatePrd as jest.Mock;
const mockReset = discoveryApi.reset as jest.Mock;
const mockGetLatest = prdApi.getLatest as jest.Mock;

const onPrdGenerated = jest.fn();
const onClose = jest.fn();

function renderPanel() {
  return render(
    <DiscoveryPanel
      workspacePath="/ws"
      onPrdGenerated={onPrdGenerated}
      onClose={onClose}
    />
  );
}

function transcript(): string[] {
  return Array.from(
    screen.getByTestId('transcript').querySelectorAll('li')
  ).map((li) => li.textContent ?? '');
}

beforeEach(() => {
  jest.clearAllMocks();
  mockStatus.mockResolvedValue({ session_id: null, state: 'idle' });
  mockStart.mockResolvedValue({
    session_id: 's-1',
    question: { text: 'What problem are you solving?' },
  });
});

// ── Start ────────────────────────────────────────────────────────────────

describe('DiscoveryPanel — start', () => {
  it('checks for an existing session before starting a new one', async () => {
    renderPanel();
    await waitFor(() => expect(mockStatus).toHaveBeenCalledWith('/ws'));
    await waitFor(() => expect(mockStart).toHaveBeenCalledWith('/ws'));
  });

  it('shows the first question once a session starts', async () => {
    renderPanel();
    await waitFor(() =>
      expect(transcript().join('\n')).toContain('What problem are you solving?')
    );
  });

  it('starts fresh anyway when the status check fails', async () => {
    // A broken status endpoint must not strand the user with no session.
    mockStatus.mockRejectedValue(new Error('offline'));
    renderPanel();
    await waitFor(() => expect(mockStart).toHaveBeenCalledWith('/ws'));
  });

  it('surfaces a failure to start rather than sitting silent', async () => {
    mockStart.mockRejectedValue({ detail: 'no API key configured' });
    renderPanel();
    await waitFor(() =>
      expect(screen.getByText('no API key configured')).toBeInTheDocument()
    );
  });

  it('opens the answer input only once discovery is under way', async () => {
    renderPanel();
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'submit-answer' })).toBeInTheDocument()
    );
  });
});

// ── Resume ───────────────────────────────────────────────────────────────

describe('DiscoveryPanel — resume', () => {
  beforeEach(() => {
    mockStatus.mockResolvedValue({
      session_id: 's-existing',
      state: 'discovering',
      progress: { answered_count: 3 },
      current_question: { text: 'Who are the users?' },
    });
  });

  it('offers to resume instead of silently starting a new session', async () => {
    renderPanel();
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /resume/i })).toBeInTheDocument()
    );
    expect(screen.getByText(/3 questions answered/i)).toBeInTheDocument();
    expect(mockStart).not.toHaveBeenCalled();
  });

  it('restores the outstanding question when resumed', async () => {
    renderPanel();
    await userEvent.click(await screen.findByRole('button', { name: /resume/i }));

    const text = transcript().join('\n');
    expect(text).toContain('Resuming your previous session');
    expect(text).toContain('Who are the users?');
    // And the input opens so the user can actually answer it.
    expect(screen.getByRole('button', { name: 'submit-answer' })).toBeEnabled();
  });

  it('singularises the count for a single answered question', async () => {
    mockStatus.mockResolvedValue({
      session_id: 's-existing',
      state: 'discovering',
      progress: { answered_count: 1 },
      current_question: { text: 'Q?' },
    });
    renderPanel();
    await waitFor(() =>
      expect(screen.getByText(/1 question answered/i)).toBeInTheDocument()
    );
    expect(screen.queryByText(/1 questions answered/i)).not.toBeInTheDocument();
  });

  it('"Start Fresh" resets the old session before starting a new one', async () => {
    mockReset.mockResolvedValue(undefined);
    renderPanel();
    await userEvent.click(await screen.findByRole('button', { name: /start fresh/i }));

    await waitFor(() => expect(mockReset).toHaveBeenCalledWith('/ws'));
    await waitFor(() => expect(mockStart).toHaveBeenCalledWith('/ws'));
  });

  it('reports a failed reset instead of leaving a dead panel', async () => {
    mockReset.mockRejectedValue({ detail: 'reset failed' });
    renderPanel();
    await userEvent.click(await screen.findByRole('button', { name: /start fresh/i }));

    await waitFor(() =>
      expect(screen.getByText('reset failed')).toBeInTheDocument()
    );
  });

  it('goes straight to the completed state for a finished session', async () => {
    mockStatus.mockResolvedValue({ session_id: 's-done', state: 'completed' });
    renderPanel();
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /generate prd/i })).toBeInTheDocument()
    );
    expect(mockStart).not.toHaveBeenCalled();
  });
});

// ── Submit answer ────────────────────────────────────────────────────────

describe('DiscoveryPanel — submit answer', () => {
  async function startedPanel() {
    renderPanel();
    await screen.findByRole('button', { name: 'submit-answer' });
  }

  it('sends the answer for the current session', async () => {
    mockSubmit.mockResolvedValue({ accepted: true, feedback: 'Good.' });
    await startedPanel();

    await userEvent.click(screen.getByRole('button', { name: 'submit-answer' }));

    await waitFor(() =>
      expect(mockSubmit).toHaveBeenCalledWith('s-1', 'my answer', '/ws')
    );
  });

  it('echoes the answer and appends the next question', async () => {
    mockSubmit.mockResolvedValue({
      accepted: true,
      feedback: 'Good.',
      next_question: { text: 'And the constraints?' },
    });
    await startedPanel();
    await userEvent.click(screen.getByRole('button', { name: 'submit-answer' }));

    await waitFor(() => {
      const text = transcript().join('\n');
      expect(text).toContain('user: my answer');
      expect(text).toContain('Good.');
      expect(text).toContain('And the constraints?');
    });
  });

  it('appends the follow-up when an answer is not accepted', async () => {
    mockSubmit.mockResolvedValue({
      accepted: false,
      feedback: 'Too vague.',
      follow_up: 'Which users specifically?',
    });
    await startedPanel();
    await userEvent.click(screen.getByRole('button', { name: 'submit-answer' }));

    await waitFor(() =>
      expect(transcript().join('\n')).toContain('Which users specifically?')
    );
  });

  it('offers PRD generation once discovery completes', async () => {
    mockSubmit.mockResolvedValue({
      accepted: true,
      feedback: 'That is everything.',
      is_complete: true,
    });
    await startedPanel();
    await userEvent.click(screen.getByRole('button', { name: 'submit-answer' }));

    await waitFor(() =>
      expect(screen.getByRole('button', { name: /generate prd/i })).toBeInTheDocument()
    );
  });

  it('surfaces a submit failure rather than swallowing it', async () => {
    // The defect this issue names: a swallowed submit error ships green.
    mockSubmit.mockRejectedValue({ detail: 'rate limited' });
    await startedPanel();
    await userEvent.click(screen.getByRole('button', { name: 'submit-answer' }));

    await waitFor(() =>
      expect(screen.getByText('rate limited')).toBeInTheDocument()
    );
  });

  it('clears the thinking state even when the submit fails', async () => {
    mockSubmit.mockRejectedValue({ detail: 'boom' });
    await startedPanel();
    await userEvent.click(screen.getByRole('button', { name: 'submit-answer' }));

    await waitFor(() =>
      expect(screen.getByTestId('thinking')).toHaveTextContent('false')
    );
    // The input must be usable again, not stuck disabled.
    expect(screen.getByRole('button', { name: 'submit-answer' })).toBeEnabled();
  });

  it('keeps the user answer in the transcript after a failure', async () => {
    mockSubmit.mockRejectedValue({ detail: 'boom' });
    await startedPanel();
    await userEvent.click(screen.getByRole('button', { name: 'submit-answer' }));

    await waitFor(() =>
      expect(transcript().join('\n')).toContain('user: my answer')
    );
  });
});

// ── Generate PRD ─────────────────────────────────────────────────────────

describe('DiscoveryPanel — generate PRD', () => {
  beforeEach(() => {
    mockStatus.mockResolvedValue({ session_id: 's-done', state: 'completed' });
  });

  it('generates then hands the full PRD to the parent', async () => {
    mockGenerate.mockResolvedValue({ prd_id: 'p-1' });
    mockGetLatest.mockResolvedValue({ id: 'p-1', content: '# PRD' });
    renderPanel();

    await userEvent.click(
      await screen.findByRole('button', { name: /generate prd/i })
    );

    await waitFor(() =>
      expect(mockGenerate).toHaveBeenCalledWith('s-done', '/ws')
    );
    // The generate response is a summary; the panel must fetch the real PRD.
    await waitFor(() => expect(mockGetLatest).toHaveBeenCalledWith('/ws'));
    expect(onPrdGenerated).toHaveBeenCalledWith({ id: 'p-1', content: '# PRD' });
  });

  it('blocks re-entry while generating', async () => {
    let resolve: (v: unknown) => void = () => {};
    mockGenerate.mockReturnValue(new Promise((r) => { resolve = r; }));
    renderPanel();

    const button = await screen.findByRole('button', { name: /generate prd/i });
    await userEvent.click(button);

    await waitFor(() =>
      expect(screen.getByRole('button', { name: /generating prd/i })).toBeDisabled()
    );
    resolve({});
  });

  it('reports a generation failure and does not notify the parent', async () => {
    mockGenerate.mockRejectedValue({ detail: 'discovery incomplete' });
    renderPanel();

    await userEvent.click(
      await screen.findByRole('button', { name: /generate prd/i })
    );

    await waitFor(() =>
      expect(screen.getByText('discovery incomplete')).toBeInTheDocument()
    );
    expect(onPrdGenerated).not.toHaveBeenCalled();
  });

  it('reports a failure to fetch the generated PRD', async () => {
    mockGenerate.mockResolvedValue({ prd_id: 'p-1' });
    mockGetLatest.mockRejectedValue({ detail: 'could not load PRD' });
    renderPanel();

    await userEvent.click(
      await screen.findByRole('button', { name: /generate prd/i })
    );

    await waitFor(() =>
      expect(screen.getByText('could not load PRD')).toBeInTheDocument()
    );
    expect(onPrdGenerated).not.toHaveBeenCalled();
  });

  it('re-enables the button after a failure', async () => {
    mockGenerate.mockRejectedValue({ detail: 'nope' });
    renderPanel();

    await userEvent.click(
      await screen.findByRole('button', { name: /generate prd/i })
    );

    await waitFor(() =>
      expect(screen.getByRole('button', { name: /generate prd/i })).toBeEnabled()
    );
  });
});

// ── Panel chrome ─────────────────────────────────────────────────────────

describe('DiscoveryPanel — chrome', () => {
  it('closes on request', async () => {
    renderPanel();
    await userEvent.click(
      await screen.findByRole('button', { name: /close discovery panel/i })
    );
    expect(onClose).toHaveBeenCalled();
  });

  it('offers start-over only once a session exists', async () => {
    renderPanel();
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /start over/i })).toBeInTheDocument()
    );
  });
});
