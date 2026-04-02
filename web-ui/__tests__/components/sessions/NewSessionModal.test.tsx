import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { NewSessionModal } from '@/components/sessions/NewSessionModal';

const defaultProps = {
  open: true,
  onOpenChange: jest.fn(),
  defaultWorkspacePath: '/home/user/projects/my-app',
  onSubmit: jest.fn().mockResolvedValue(undefined),
};

beforeEach(() => {
  jest.clearAllMocks();
});

describe('NewSessionModal', () => {
  it('renders when open is true', () => {
    render(<NewSessionModal {...defaultProps} />);
    expect(screen.getByText('New Session')).toBeInTheDocument();
  });

  it('does not render when open is false', () => {
    render(<NewSessionModal {...defaultProps} open={false} />);
    expect(screen.queryByText('New Session')).not.toBeInTheDocument();
  });

  it('pre-fills workspace path from prop', () => {
    render(<NewSessionModal {...defaultProps} />);
    const input = screen.getByLabelText(/workspace/i);
    expect(input).toHaveValue('/home/user/projects/my-app');
  });

  it('defaults model to claude-sonnet-4-6', () => {
    render(<NewSessionModal {...defaultProps} />);
    // The select trigger should show the default value
    expect(screen.getByText('claude-sonnet-4-6')).toBeInTheDocument();
  });

  it('calls onSubmit with workspace_path and model on submit', async () => {
    const user = userEvent.setup();
    render(<NewSessionModal {...defaultProps} />);
    await user.click(screen.getByRole('button', { name: /start session/i }));
    await waitFor(() => {
      expect(defaultProps.onSubmit).toHaveBeenCalledWith({
        workspace_path: '/home/user/projects/my-app',
        model: 'claude-sonnet-4-6',
      });
    });
  });

  it('disables Start Session button while submitting', async () => {
    const onSubmit = jest.fn().mockReturnValue(new Promise(() => {})); // never resolves
    const user = userEvent.setup();
    render(<NewSessionModal {...defaultProps} onSubmit={onSubmit} />);
    await user.click(screen.getByRole('button', { name: /start session/i }));
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /start session/i })).toBeDisabled();
    });
  });

  it('allows editing the workspace path', async () => {
    const user = userEvent.setup();
    render(<NewSessionModal {...defaultProps} />);
    const input = screen.getByLabelText(/workspace/i);
    await user.clear(input);
    await user.type(input, '/other/path');
    await user.click(screen.getByRole('button', { name: /start session/i }));
    await waitFor(() => {
      expect(defaultProps.onSubmit).toHaveBeenCalledWith({
        workspace_path: '/other/path',
        model: 'claude-sonnet-4-6',
      });
    });
  });
});
