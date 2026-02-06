import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { DiscoveryInput } from '@/components/prd/DiscoveryInput';

describe('DiscoveryInput', () => {
  const defaultProps = {
    onSubmit: jest.fn(),
    disabled: false,
  };

  beforeEach(() => jest.clearAllMocks());

  it('renders textarea and send button', () => {
    render(<DiscoveryInput {...defaultProps} />);
    expect(screen.getByPlaceholderText('Type your answer...')).toBeInTheDocument();
    expect(screen.getByRole('button')).toBeInTheDocument();
  });

  it('renders custom placeholder', () => {
    render(<DiscoveryInput {...defaultProps} placeholder="Custom placeholder" />);
    expect(screen.getByPlaceholderText('Custom placeholder')).toBeInTheDocument();
  });

  it('shows Ctrl+Enter hint', () => {
    render(<DiscoveryInput {...defaultProps} />);
    expect(screen.getByText(/ctrl\+enter/i)).toBeInTheDocument();
  });

  it('disables send button when input is empty', () => {
    render(<DiscoveryInput {...defaultProps} />);
    expect(screen.getByRole('button')).toBeDisabled();
  });

  it('enables send button when input has text', async () => {
    const user = userEvent.setup();
    render(<DiscoveryInput {...defaultProps} />);

    await user.type(screen.getByPlaceholderText('Type your answer...'), 'Hello');
    expect(screen.getByRole('button')).toBeEnabled();
  });

  it('calls onSubmit with trimmed text on button click', async () => {
    const user = userEvent.setup();
    render(<DiscoveryInput {...defaultProps} />);

    await user.type(screen.getByPlaceholderText('Type your answer...'), '  My answer  ');
    await user.click(screen.getByRole('button'));

    expect(defaultProps.onSubmit).toHaveBeenCalledWith('My answer');
  });

  it('clears input after submit', async () => {
    const user = userEvent.setup();
    render(<DiscoveryInput {...defaultProps} />);

    const textarea = screen.getByPlaceholderText('Type your answer...');
    await user.type(textarea, 'My answer');
    await user.click(screen.getByRole('button'));

    expect(textarea).toHaveValue('');
  });

  it('submits on Ctrl+Enter', async () => {
    const user = userEvent.setup();
    render(<DiscoveryInput {...defaultProps} />);

    const textarea = screen.getByPlaceholderText('Type your answer...');
    await user.type(textarea, 'My answer');
    await user.keyboard('{Control>}{Enter}{/Control}');

    expect(defaultProps.onSubmit).toHaveBeenCalledWith('My answer');
  });

  it('disables textarea and button when disabled prop is true', () => {
    render(<DiscoveryInput {...defaultProps} disabled />);
    expect(screen.getByPlaceholderText('Type your answer...')).toBeDisabled();
    expect(screen.getByRole('button')).toBeDisabled();
  });

  it('does not submit whitespace-only input', async () => {
    const user = userEvent.setup();
    render(<DiscoveryInput {...defaultProps} />);

    await user.type(screen.getByPlaceholderText('Type your answer...'), '   ');
    // Button should be disabled for whitespace-only
    expect(screen.getByRole('button')).toBeDisabled();
  });
});
