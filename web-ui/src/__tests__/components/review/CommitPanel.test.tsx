/**
 * CommitPanel behavioural coverage (issue #964).
 *
 * The Ship surface had no unit tests at all: CommitPanel is the control that
 * turns a reviewed diff into a commit and optionally a PR, and CI green said
 * nothing about whether it worked.
 *
 * These assert the contract the review page depends on — which callback fires,
 * with what arguments, and when the controls are disabled — rather than markup.
 */
import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { CommitPanel } from '@/components/review/CommitPanel';

function setup(overrides: Partial<React.ComponentProps<typeof CommitPanel>> = {}) {
  const props: React.ComponentProps<typeof CommitPanel> = {
    commitMessage: 'feat: add thing',
    onCommitMessageChange: jest.fn(),
    onGenerateMessage: jest.fn(),
    onCommit: jest.fn(),
    isGenerating: false,
    isCommitting: false,
    isCreatingPR: false,
    changedFiles: ['src/a.ts', 'src/b.ts'],
    onCreatePR: jest.fn(),
    ...overrides,
  };
  render(<CommitPanel {...props} />);
  return props;
}

describe('CommitPanel — commit flow', () => {
  it('calls onCommit when the commit button is pressed', async () => {
    const props = setup();
    await userEvent.click(screen.getByRole('button', { name: /^commit$/i }));
    expect(props.onCommit).toHaveBeenCalledTimes(1);
  });

  it('reports every keystroke in the message box', () => {
    const props = setup({ commitMessage: '' });
    fireEvent.change(screen.getByLabelText(/commit message/i), {
      target: { value: 'fix: something' },
    });
    expect(props.onCommitMessageChange).toHaveBeenCalledWith('fix: something');
  });

  it('refuses to commit an empty message', () => {
    setup({ commitMessage: '   ' });
    expect(screen.getByRole('button', { name: /^commit$/i })).toBeDisabled();
  });

  it('shows progress and blocks re-entry while committing', () => {
    const props = setup({ isCommitting: true });
    const button = screen.getByRole('button', { name: /committing/i });
    expect(button).toBeDisabled();
    fireEvent.click(button);
    expect(props.onCommit).not.toHaveBeenCalled();
  });

  it('lists the files that will be committed, with a count', () => {
    setup({ changedFiles: ['src/a.ts', 'src/b.ts', 'src/c.ts'] });
    expect(screen.getByText('3')).toBeInTheDocument();
    expect(screen.getByText('src/a.ts')).toBeInTheDocument();
    expect(screen.getByText('src/c.ts')).toBeInTheDocument();
  });

  it('says so when there is nothing to commit', () => {
    setup({ changedFiles: [] });
    expect(screen.getByText(/no changed files/i)).toBeInTheDocument();
  });
});

describe('CommitPanel — message generation', () => {
  it('calls onGenerateMessage', async () => {
    const props = setup();
    await userEvent.click(screen.getByRole('button', { name: /generate message/i }));
    expect(props.onGenerateMessage).toHaveBeenCalledTimes(1);
  });

  it('is disabled while a generation is in flight', () => {
    setup({ isGenerating: true });
    expect(screen.getByRole('button', { name: /generate message/i })).toBeDisabled();
  });
});

describe('CommitPanel — pull request flow', () => {
  it('keeps the PR form hidden until it is opted into', async () => {
    setup();
    expect(screen.queryByLabelText(/pr title/i)).not.toBeInTheDocument();

    await userEvent.click(screen.getByLabelText(/create pull request/i));
    expect(screen.getByLabelText(/pr title/i)).toBeInTheDocument();
  });

  it('passes the title and body through to onCreatePR', async () => {
    const props = setup();
    await userEvent.click(screen.getByLabelText(/create pull request/i));

    fireEvent.change(screen.getByLabelText(/pr title/i), {
      target: { value: 'Add the thing' },
    });
    fireEvent.change(screen.getByLabelText(/description/i), {
      target: { value: 'It does the thing.' },
    });
    await userEvent.click(screen.getByRole('button', { name: /create pr/i }));

    expect(props.onCreatePR).toHaveBeenCalledWith('Add the thing', 'It does the thing.');
  });

  it('refuses to open a PR with no title', async () => {
    setup();
    await userEvent.click(screen.getByLabelText(/create pull request/i));
    expect(screen.getByRole('button', { name: /create pr/i })).toBeDisabled();
  });

  it('allows an empty body', async () => {
    const props = setup();
    await userEvent.click(screen.getByLabelText(/create pull request/i));
    fireEvent.change(screen.getByLabelText(/pr title/i), {
      target: { value: 'Title only' },
    });
    await userEvent.click(screen.getByRole('button', { name: /create pr/i }));
    expect(props.onCreatePR).toHaveBeenCalledWith('Title only', '');
  });

  it('blocks re-entry while a PR is being created', async () => {
    const props = setup({ isCreatingPR: true });
    await userEvent.click(screen.getByLabelText(/create pull request/i));

    const button = screen.getByRole('button', { name: /creating pr/i });
    expect(button).toBeDisabled();
    fireEvent.click(button);
    expect(props.onCreatePR).not.toHaveBeenCalled();
  });
});
