/**
 * Tests for the /login page (issue #336):
 * - renders email + password form and a sign-in button;
 * - submits credentials via auth.login then redirects to /;
 * - surfaces a friendly error when login fails;
 * - the "create the first account" toggle reveals the register flow, which
 *   calls register() then auto-logs-in and redirects.
 */
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import LoginPage from '@/app/login/page';

const pushMock = jest.fn();
jest.mock('next/navigation', () => ({
  useRouter: () => ({ push: pushMock, replace: jest.fn() }),
}));

const loginMock = jest.fn();
const registerMock = jest.fn();
jest.mock('@/lib/auth', () => ({
  login: (...args: unknown[]) => loginMock(...args),
  register: (...args: unknown[]) => registerMock(...args),
}));

beforeEach(() => {
  pushMock.mockReset();
  loginMock.mockReset();
  registerMock.mockReset();
});

describe('LoginPage', () => {
  it('renders the email and password fields and a sign-in button', () => {
    render(<LoginPage />);
    expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /sign in/i })).toBeInTheDocument();
  });

  it('submits credentials and redirects to / on success', async () => {
    loginMock.mockResolvedValueOnce('jwt-abc');
    render(<LoginPage />);

    fireEvent.change(screen.getByLabelText(/email/i), {
      target: { value: 'user@example.com' },
    });
    fireEvent.change(screen.getByLabelText(/password/i), {
      target: { value: 'pw123' },
    });
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }));

    await waitFor(() => {
      expect(loginMock).toHaveBeenCalledWith('user@example.com', 'pw123');
    });
    await waitFor(() => {
      expect(pushMock).toHaveBeenCalledWith('/');
    });
  });

  it('shows an error message when login fails', async () => {
    loginMock.mockRejectedValueOnce(new Error('Invalid email or password.'));
    render(<LoginPage />);

    fireEvent.change(screen.getByLabelText(/email/i), {
      target: { value: 'user@example.com' },
    });
    fireEvent.change(screen.getByLabelText(/password/i), {
      target: { value: 'bad' },
    });
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }));

    expect(await screen.findByText(/invalid email or password/i)).toBeInTheDocument();
    expect(pushMock).not.toHaveBeenCalled();
  });

  it('register flow: toggles, registers, auto-logs-in, and redirects', async () => {
    registerMock.mockResolvedValueOnce(undefined);
    loginMock.mockResolvedValueOnce('jwt-new');
    render(<LoginPage />);

    // Reveal the register flow.
    fireEvent.click(screen.getByRole('button', { name: /create the first account/i }));

    fireEvent.change(screen.getByLabelText(/email/i), {
      target: { value: 'first@example.com' },
    });
    fireEvent.change(screen.getByLabelText(/password/i), {
      target: { value: 'pw123' },
    });
    fireEvent.click(screen.getByRole('button', { name: /create account/i }));

    await waitFor(() => {
      expect(registerMock).toHaveBeenCalledWith('first@example.com', 'pw123');
    });
    await waitFor(() => {
      expect(loginMock).toHaveBeenCalledWith('first@example.com', 'pw123');
    });
    await waitFor(() => {
      expect(pushMock).toHaveBeenCalledWith('/');
    });
  });
});
