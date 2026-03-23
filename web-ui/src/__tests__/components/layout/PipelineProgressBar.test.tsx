import React from 'react';
import { render, screen } from '@testing-library/react';
import { usePathname } from 'next/navigation';
import { PipelineProgressBar } from '@/components/layout/PipelineProgressBar';
import { usePipelineStatus } from '@/hooks/usePipelineStatus';

jest.mock('@/hooks/usePipelineStatus');
jest.mock('next/navigation', () => ({
  usePathname: jest.fn(),
  useRouter: jest.fn(() => ({ push: jest.fn() })),
}));

const mockUsePipelineStatus = usePipelineStatus as jest.MockedFunction<typeof usePipelineStatus>;
const mockUsePathname = usePathname as jest.MockedFunction<typeof usePathname>;

const allIncomplete = {
  think: { isComplete: false, isLoading: false },
  build: { isComplete: false, isLoading: false },
  prove: { isComplete: false, isLoading: false },
  ship: { isComplete: false, isLoading: false },
};

const allComplete = {
  think: { isComplete: true, isLoading: false },
  build: { isComplete: true, isLoading: false },
  prove: { isComplete: true, isLoading: false },
  ship: { isComplete: true, isLoading: false },
};

describe('PipelineProgressBar', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders all four phase labels on desktop', () => {
    mockUsePathname.mockReturnValue('/prd');
    mockUsePipelineStatus.mockReturnValue(allIncomplete);

    render(<PipelineProgressBar />);

    expect(screen.getByText('Think')).toBeInTheDocument();
    expect(screen.getByText('Build')).toBeInTheDocument();
    expect(screen.getByText('Prove')).toBeInTheDocument();
    expect(screen.getByText('Ship')).toBeInTheDocument();
  });

  it('returns null on root path /', () => {
    mockUsePathname.mockReturnValue('/');
    mockUsePipelineStatus.mockReturnValue(allIncomplete);

    const { container } = render(<PipelineProgressBar />);
    expect(container.firstChild).toBeNull();
  });

  it('highlights the Think phase when on /prd', () => {
    mockUsePathname.mockReturnValue('/prd');
    mockUsePipelineStatus.mockReturnValue(allIncomplete);

    render(<PipelineProgressBar />);

    // Think link should have active styling indicator
    const thinkLink = screen.getByRole('link', { name: /think/i });
    expect(thinkLink).toHaveAttribute('href', '/prd');
  });

  it('highlights the Build phase when on /tasks', () => {
    mockUsePathname.mockReturnValue('/tasks');
    mockUsePipelineStatus.mockReturnValue(allIncomplete);

    render(<PipelineProgressBar />);

    const buildLink = screen.getByRole('link', { name: /build/i });
    expect(buildLink).toHaveAttribute('href', '/tasks');
  });

  it('highlights the Build phase when on /execution', () => {
    mockUsePathname.mockReturnValue('/execution');
    mockUsePipelineStatus.mockReturnValue(allIncomplete);

    render(<PipelineProgressBar />);

    const buildLink = screen.getByRole('link', { name: /build/i });
    expect(buildLink).toHaveAttribute('href', '/tasks');
  });

  it('highlights the Build phase when on /blockers', () => {
    mockUsePathname.mockReturnValue('/blockers');
    mockUsePipelineStatus.mockReturnValue(allIncomplete);

    render(<PipelineProgressBar />);

    const buildLink = screen.getByRole('link', { name: /build/i });
    expect(buildLink).toHaveAttribute('href', '/tasks');
  });

  it('highlights the Prove phase when on /proof', () => {
    mockUsePathname.mockReturnValue('/proof');
    mockUsePipelineStatus.mockReturnValue(allIncomplete);

    render(<PipelineProgressBar />);

    const proveLink = screen.getByRole('link', { name: /prove/i });
    expect(proveLink).toHaveAttribute('href', '/proof');
  });

  it('highlights the Ship phase when on /review', () => {
    mockUsePathname.mockReturnValue('/review');
    mockUsePipelineStatus.mockReturnValue(allIncomplete);

    render(<PipelineProgressBar />);

    const shipLink = screen.getByRole('link', { name: /ship/i });
    expect(shipLink).toHaveAttribute('href', '/review');
  });

  it('shows checkmark icon for completed phases', () => {
    mockUsePathname.mockReturnValue('/tasks');
    mockUsePipelineStatus.mockReturnValue({
      ...allIncomplete,
      think: { isComplete: true, isLoading: false },
    });

    render(<PipelineProgressBar />);

    // Completed phase should show check icon
    expect(screen.getByTestId('icon-Tick01Icon')).toBeInTheDocument();
  });

  it('shows all checkmarks when all phases complete', () => {
    mockUsePathname.mockReturnValue('/review');
    mockUsePipelineStatus.mockReturnValue(allComplete);

    render(<PipelineProgressBar />);

    expect(screen.getAllByTestId('icon-Tick01Icon')).toHaveLength(4);
  });

  it('each phase link navigates to correct route', () => {
    mockUsePathname.mockReturnValue('/prd');
    mockUsePipelineStatus.mockReturnValue(allIncomplete);

    render(<PipelineProgressBar />);

    expect(screen.getByRole('link', { name: /think/i })).toHaveAttribute('href', '/prd');
    expect(screen.getByRole('link', { name: /build/i })).toHaveAttribute('href', '/tasks');
    expect(screen.getByRole('link', { name: /prove/i })).toHaveAttribute('href', '/proof');
    expect(screen.getByRole('link', { name: /ship/i })).toHaveAttribute('href', '/review');
  });
});
