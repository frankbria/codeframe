import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { PRDHeader } from '@/components/prd/PRDHeader';
import type { PrdResponse } from '@/types';

const mockPrd: PrdResponse = {
  id: 'prd-1',
  workspace_id: 'ws-1',
  title: 'My Product PRD',
  content: '# PRD Content',
  metadata: {},
  created_at: '2026-01-15T10:00:00Z',
  version: 3,
  parent_id: null,
  change_summary: null,
  chain_id: 'chain-1',
};

describe('PRDHeader', () => {
  const defaultProps = {
    prd: null as PrdResponse | null,
    onUploadPrd: jest.fn(),
    onStartDiscovery: jest.fn(),
    onGenerateTasks: jest.fn(),
  };

  beforeEach(() => jest.clearAllMocks());

  it('renders default title when no PRD', () => {
    render(<PRDHeader {...defaultProps} />);
    expect(screen.getByText('Product Requirements')).toBeInTheDocument();
  });

  it('renders PRD title and version when PRD exists', () => {
    render(<PRDHeader {...defaultProps} prd={mockPrd} />);
    expect(screen.getByText('My Product PRD')).toBeInTheDocument();
    expect(screen.getByText(/Version 3/)).toBeInTheDocument();
  });

  it('renders Upload, Discovery, and Generate Tasks buttons', () => {
    render(<PRDHeader {...defaultProps} />);
    expect(screen.getByRole('button', { name: /upload prd/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /discovery/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /generate tasks/i })).toBeInTheDocument();
  });

  it('shows "Upload New" text when PRD exists', () => {
    render(<PRDHeader {...defaultProps} prd={mockPrd} />);
    expect(screen.getByRole('button', { name: /upload new/i })).toBeInTheDocument();
  });

  it('disables Generate Tasks when no PRD', () => {
    render(<PRDHeader {...defaultProps} />);
    expect(screen.getByRole('button', { name: /generate tasks/i })).toBeDisabled();
  });

  it('enables Generate Tasks when PRD exists', () => {
    render(<PRDHeader {...defaultProps} prd={mockPrd} />);
    expect(screen.getByRole('button', { name: /generate tasks/i })).toBeEnabled();
  });

  it('shows loading state when generating tasks', () => {
    render(<PRDHeader {...defaultProps} prd={mockPrd} isGeneratingTasks />);
    expect(screen.getByRole('button', { name: /generating/i })).toBeDisabled();
  });

  it('calls onUploadPrd when Upload button clicked', async () => {
    const user = userEvent.setup();
    render(<PRDHeader {...defaultProps} />);
    await user.click(screen.getByRole('button', { name: /upload prd/i }));
    expect(defaultProps.onUploadPrd).toHaveBeenCalledTimes(1);
  });

  it('calls onStartDiscovery when Discovery button clicked', async () => {
    const user = userEvent.setup();
    render(<PRDHeader {...defaultProps} />);
    await user.click(screen.getByRole('button', { name: /discovery/i }));
    expect(defaultProps.onStartDiscovery).toHaveBeenCalledTimes(1);
  });

  it('calls onGenerateTasks when Generate Tasks button clicked', async () => {
    const user = userEvent.setup();
    render(<PRDHeader {...defaultProps} prd={mockPrd} />);
    await user.click(screen.getByRole('button', { name: /generate tasks/i }));
    expect(defaultProps.onGenerateTasks).toHaveBeenCalledTimes(1);
  });
});
