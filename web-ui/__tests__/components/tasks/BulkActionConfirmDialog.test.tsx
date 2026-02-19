import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BulkActionConfirmDialog } from '@/components/tasks/BulkActionConfirmDialog';

const defaultProps = {
  open: true,
  onOpenChange: jest.fn(),
  actionType: 'execute' as const,
  taskCount: 3,
  onConfirm: jest.fn(),
  isLoading: false,
};

beforeEach(() => {
  jest.clearAllMocks();
});

describe('BulkActionConfirmDialog', () => {
  it('renders execute confirmation with correct title and description', () => {
    render(<BulkActionConfirmDialog {...defaultProps} actionType="execute" taskCount={5} />);
    expect(screen.getByText('Execute Tasks')).toBeInTheDocument();
    expect(screen.getByText(/execute 5 task\(s\)/i)).toBeInTheDocument();
  });

  it('renders stop confirmation with correct title and description', () => {
    render(<BulkActionConfirmDialog {...defaultProps} actionType="stop" taskCount={2} />);
    expect(screen.getByText('Stop Tasks')).toBeInTheDocument();
    expect(screen.getByText(/stop 2 running task\(s\)/i)).toBeInTheDocument();
  });

  it('renders reset confirmation with correct title and description', () => {
    render(<BulkActionConfirmDialog {...defaultProps} actionType="reset" taskCount={4} />);
    expect(screen.getByText('Reset Tasks')).toBeInTheDocument();
    expect(screen.getByText(/reset 4 failed task\(s\)/i)).toBeInTheDocument();
  });

  it('calls onConfirm when confirm button is clicked', async () => {
    const user = userEvent.setup();
    render(<BulkActionConfirmDialog {...defaultProps} />);
    await user.click(screen.getByRole('button', { name: /confirm/i }));
    expect(defaultProps.onConfirm).toHaveBeenCalledTimes(1);
  });

  it('calls onOpenChange(false) when cancel button is clicked', async () => {
    const user = userEvent.setup();
    render(<BulkActionConfirmDialog {...defaultProps} />);
    await user.click(screen.getByRole('button', { name: /cancel/i }));
    expect(defaultProps.onOpenChange).toHaveBeenCalledWith(false);
  });

  it('disables confirm button when isLoading is true', () => {
    render(<BulkActionConfirmDialog {...defaultProps} isLoading={true} />);
    const confirmBtn = screen.getByRole('button', { name: /confirm/i });
    expect(confirmBtn).toBeDisabled();
  });

  it('does not render when open is false', () => {
    render(<BulkActionConfirmDialog {...defaultProps} open={false} />);
    expect(screen.queryByText('Execute Tasks')).not.toBeInTheDocument();
  });

  it('shows destructive styling for stop action confirm button', () => {
    render(<BulkActionConfirmDialog {...defaultProps} actionType="stop" />);
    const confirmBtn = screen.getByRole('button', { name: /confirm/i });
    expect(confirmBtn).toHaveClass('bg-destructive');
  });
});
