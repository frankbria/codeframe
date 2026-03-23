import { render, screen, fireEvent } from '@testing-library/react';
import { OnboardingCard } from '@/components/workspace/OnboardingCard';
import * as storage from '@/lib/workspace-storage';

// Mock next/link to render as plain anchor
jest.mock('next/link', () => {
  const MockLink = ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  );
  MockLink.displayName = 'MockLink';
  return MockLink;
});

jest.mock('@/lib/workspace-storage', () => ({
  getOnboardingDismissed: jest.fn(),
  setOnboardingDismissed: jest.fn(),
}));

const mockGetOnboardingDismissed = storage.getOnboardingDismissed as jest.MockedFunction<typeof storage.getOnboardingDismissed>;
const mockSetOnboardingDismissed = storage.setOnboardingDismissed as jest.MockedFunction<typeof storage.setOnboardingDismissed>;

const WORKSPACE_PATH = '/home/user/my-project';

describe('OnboardingCard', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockGetOnboardingDismissed.mockReturnValue(false);
  });

  it('renders when not dismissed', () => {
    render(<OnboardingCard workspacePath={WORKSPACE_PATH} />);
    expect(screen.getByRole('link', { name: /get started/i })).toBeInTheDocument();
  });

  it('shows the 4-step pipeline labels', () => {
    render(<OnboardingCard workspacePath={WORKSPACE_PATH} />);
    expect(screen.getByText('Think')).toBeInTheDocument();
    expect(screen.getByText('Build')).toBeInTheDocument();
    expect(screen.getByText('Prove')).toBeInTheDocument();
    expect(screen.getByText('Ship')).toBeInTheDocument();
  });

  it('CTA links to /prd', () => {
    render(<OnboardingCard workspacePath={WORKSPACE_PATH} />);
    const link = screen.getByRole('link', { name: /get started/i });
    expect(link).toHaveAttribute('href', '/prd');
  });

  it('does not render when already dismissed', () => {
    mockGetOnboardingDismissed.mockReturnValue(true);
    const { container } = render(<OnboardingCard workspacePath={WORKSPACE_PATH} />);
    expect(container.firstChild).toBeNull();
  });

  it('calls setOnboardingDismissed with workspace path on dismiss', () => {
    render(<OnboardingCard workspacePath={WORKSPACE_PATH} />);
    const dismissBtn = screen.getByRole('button', { name: /dismiss/i });
    fireEvent.click(dismissBtn);
    expect(mockSetOnboardingDismissed).toHaveBeenCalledWith(WORKSPACE_PATH);
  });

  it('hides card after dismiss click', () => {
    render(<OnboardingCard workspacePath={WORKSPACE_PATH} />);
    const dismissBtn = screen.getByRole('button', { name: /dismiss/i });
    fireEvent.click(dismissBtn);
    expect(screen.queryByText(/get started/i)).not.toBeInTheDocument();
  });

  it('reads dismiss state using the workspace path', () => {
    render(<OnboardingCard workspacePath={WORKSPACE_PATH} />);
    expect(mockGetOnboardingDismissed).toHaveBeenCalledWith(WORKSPACE_PATH);
  });
});
