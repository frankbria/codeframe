import { render, screen, act, fireEvent } from '@testing-library/react';
import { TaskFilters } from '@/components/tasks/TaskFilters';

const defaultProps = {
  searchQuery: '',
  onSearchChange: jest.fn(),
  statusFilter: null,
  onStatusFilter: jest.fn(),
};

beforeEach(() => {
  jest.useFakeTimers();
  jest.clearAllMocks();
});

afterEach(() => {
  jest.useRealTimers();
});

describe('TaskFilters', () => {
  it('renders search input and status pills', () => {
    render(<TaskFilters {...defaultProps} />);
    expect(screen.getByPlaceholderText('Search tasks...')).toBeInTheDocument();
    expect(screen.getByText('Backlog')).toBeInTheDocument();
    expect(screen.getByText('Ready')).toBeInTheDocument();
    expect(screen.getByText('Done')).toBeInTheDocument();
  });

  it('debounces search input by 300ms', () => {
    render(<TaskFilters {...defaultProps} />);
    const input = screen.getByPlaceholderText('Search tasks...');

    // Type a value
    fireEvent.change(input, { target: { value: 'login' } });

    // Should not have called onSearchChange yet (within debounce window)
    act(() => { jest.advanceTimersByTime(200); });
    // Initial mount timer may fire with '', so clear those calls
    const callsBeforeDebounce = defaultProps.onSearchChange.mock.calls.filter(
      (call: string[]) => call[0] === 'login'
    );
    expect(callsBeforeDebounce).toHaveLength(0);

    // After 300ms, debounce fires
    act(() => { jest.advanceTimersByTime(150); });
    expect(defaultProps.onSearchChange).toHaveBeenCalledWith('login');
  });

  it('calls onStatusFilter when clicking a status pill', () => {
    render(<TaskFilters {...defaultProps} />);
    const readyButton = screen.getByText('Ready').closest('button')!;
    fireEvent.click(readyButton);
    expect(defaultProps.onStatusFilter).toHaveBeenCalledWith('READY');
  });

  it('toggles status filter off when clicking active pill', () => {
    render(<TaskFilters {...defaultProps} statusFilter="READY" />);
    const readyButton = screen.getByText('Ready').closest('button')!;
    fireEvent.click(readyButton);
    expect(defaultProps.onStatusFilter).toHaveBeenCalledWith(null);
  });

  it('shows Clear button when status filter is active', () => {
    render(<TaskFilters {...defaultProps} statusFilter="DONE" />);
    expect(screen.getByText('Clear')).toBeInTheDocument();
  });

  it('hides Clear button when no status filter', () => {
    render(<TaskFilters {...defaultProps} />);
    expect(screen.queryByText('Clear')).not.toBeInTheDocument();
  });
});
