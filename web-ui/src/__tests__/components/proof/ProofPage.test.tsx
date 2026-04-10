import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import useSWR from 'swr';
import ProofPage from '@/app/proof/page';
import * as storage from '@/lib/workspace-storage';
import type { ProofRequirementListResponse, ProofReqStatus, ProofSeverity } from '@/types';

// ── Mocks ────────────────────────────────────────────────────────────────

jest.mock('swr');
jest.mock('next/navigation', () => ({
  useSearchParams: () => ({ get: () => null }),
}));
jest.mock('@/lib/workspace-storage', () => ({
  getSelectedWorkspacePath: jest.fn(),
}));
jest.mock('@/lib/api', () => ({
  proofApi: {
    listRequirements: jest.fn(),
    waiveRequirement: jest.fn(),
  },
}));
jest.mock('@/components/proof', () => ({
  ProofStatusBadge: ({ status }: { status: string }) => <span data-testid="status-badge">{status}</span>,
  WaiveDialog: () => null,
  GateRunPanel: () => null,
  GateRunBanner: () => null,
  GateEvidencePanel: () => null,
  RunHistoryPanel: () => null,
  CaptureGlitchModal: () => null,
}));
jest.mock('next/link', () => {
  const MockLink = ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  );
  MockLink.displayName = 'MockLink';
  return MockLink;
});

// ── Helpers ───────────────────────────────────────────────────────────────

const mockUseSWR = useSWR as jest.MockedFunction<typeof useSWR>;
const mockGetWorkspace = storage.getSelectedWorkspacePath as jest.MockedFunction<
  typeof storage.getSelectedWorkspacePath
>;

const WORKSPACE = '/home/user/project';

function makeReq(overrides: Partial<{
  id: string; title: string; severity: ProofSeverity; status: ProofReqStatus;
  glitch_type: string | null; created_at: string;
}> = {}) {
  return {
    id: overrides.id ?? 'REQ-001',
    title: overrides.title ?? 'Test requirement',
    description: 'desc',
    severity: overrides.severity ?? ('medium' as ProofSeverity),
    source: 'manual',
    status: overrides.status ?? ('open' as ProofReqStatus),
    glitch_type: overrides.glitch_type ?? null,
    obligations: [],
    evidence_rules: [],
    waiver: null,
    created_at: overrides.created_at ?? '2026-01-01T00:00:00Z',
    satisfied_at: null,
    created_by: 'user',
    source_issue: null,
    related_reqs: [],
  };
}

const mockData: ProofRequirementListResponse = {
  requirements: [
    makeReq({ id: 'REQ-001', title: 'Alpha', severity: 'low', status: 'satisfied', glitch_type: 'regression', created_at: '2026-01-03T00:00:00Z' }),
    makeReq({ id: 'REQ-002', title: 'Beta',  severity: 'critical', status: 'open', glitch_type: 'security', created_at: '2026-01-01T00:00:00Z' }),
    makeReq({ id: 'REQ-003', title: 'Gamma', severity: 'high', status: 'waived', glitch_type: 'regression', created_at: '2026-01-02T00:00:00Z' }),
    makeReq({ id: 'REQ-004', title: 'Delta', severity: 'medium', status: 'open', glitch_type: 'performance', created_at: '2026-01-04T00:00:00Z' }),
  ],
  total: 4,
  by_status: { open: 2, satisfied: 1, waived: 1 },
};

function setup(data: ProofRequirementListResponse = mockData) {
  mockGetWorkspace.mockReturnValue(WORKSPACE);
  mockUseSWR.mockReturnValue({
    data,
    error: undefined,
    isLoading: false,
    mutate: jest.fn(),
  } as unknown as ReturnType<typeof useSWR>);
  render(<ProofPage />);
}

// ── Tests ─────────────────────────────────────────────────────────────────

describe('ProofPage — filter controls', () => {
  beforeEach(() => jest.clearAllMocks());

  it('renders search input', () => {
    setup();
    expect(screen.getByPlaceholderText(/search/i)).toBeInTheDocument();
  });

  it('renders Status filter dropdown', () => {
    setup();
    expect(screen.getByRole('combobox', { name: /status/i })).toBeInTheDocument();
  });

  it('renders Severity filter dropdown', () => {
    setup();
    expect(screen.getByRole('combobox', { name: /severity/i })).toBeInTheDocument();
  });

  it('renders Glitch Type filter dropdown', () => {
    setup();
    expect(screen.getByRole('combobox', { name: /glitch type/i })).toBeInTheDocument();
  });

  it('renders Reset filters button when a filter is active', () => {
    setup();
    fireEvent.change(screen.getByPlaceholderText(/search/i), { target: { value: 'a' } });
    expect(screen.getByRole('button', { name: /reset/i })).toBeInTheDocument();
  });
});

describe('ProofPage — default sort', () => {
  beforeEach(() => jest.clearAllMocks());

  it('shows open requirements before satisfied (default sort by status)', () => {
    setup();
    const rows = screen.getAllByTestId('status-badge');
    const statuses = rows.map((r) => r.textContent);
    const firstOpen = statuses.indexOf('open');
    const firstSatisfied = statuses.indexOf('satisfied');
    expect(firstOpen).toBeLessThan(firstSatisfied);
  });

  it('within open requirements, shows critical before medium', () => {
    setup();
    const cells = screen.getAllByRole('cell');
    const cellTexts = cells.map((c) => c.textContent?.trim());
    const critIdx = cellTexts.findIndex((t) => t === 'critical');
    const medIdx = cellTexts.findIndex((t) => t === 'medium');
    expect(critIdx).toBeLessThan(medIdx);
  });
});

describe('ProofPage — sort by column', () => {
  beforeEach(() => jest.clearAllMocks());

  it('sorts by ID ascending when ID header is clicked once', () => {
    setup();
    fireEvent.click(screen.getByRole('button', { name: /sort by id/i }));
    const cells = screen.getAllByRole('cell');
    const ids = cells.filter((c) => /REQ-\d+/.test(c.textContent ?? ''))
                      .map((c) => c.textContent?.trim());
    expect(ids[0]).toBe('REQ-001');
    expect(ids[1]).toBe('REQ-002');
  });

  it('sorts by ID descending when ID header is clicked twice', () => {
    setup();
    fireEvent.click(screen.getByRole('button', { name: /sort by id/i }));
    fireEvent.click(screen.getByRole('button', { name: /sort by id/i }));
    const cells = screen.getAllByRole('cell');
    const ids = cells.filter((c) => /REQ-\d+/.test(c.textContent ?? ''))
                      .map((c) => c.textContent?.trim());
    expect(ids[0]).toBe('REQ-004');
  });

  it('shows aria-sort on the th element when a column is sorted', () => {
    setup();
    fireEvent.click(screen.getByRole('button', { name: /sort by id/i }));
    const th = screen.getByRole('button', { name: /sort by id/i }).closest('th');
    expect(th).toHaveAttribute('aria-sort', 'ascending');
  });
});

describe('ProofPage — search filter', () => {
  beforeEach(() => jest.clearAllMocks());

  it('filters rows by ID substring', () => {
    setup();
    fireEvent.change(screen.getByPlaceholderText(/search/i), { target: { value: 'REQ-002' } });
    expect(screen.getAllByTestId('status-badge')).toHaveLength(1);
    expect(screen.getByText('Beta')).toBeInTheDocument();
  });

  it('filters rows by title substring (case-insensitive)', () => {
    setup();
    fireEvent.change(screen.getByPlaceholderText(/search/i), { target: { value: 'gamma' } });
    expect(screen.getAllByTestId('status-badge')).toHaveLength(1);
    expect(screen.getByText('Gamma')).toBeInTheDocument();
  });

  it('shows all rows when search is cleared', () => {
    setup();
    fireEvent.change(screen.getByPlaceholderText(/search/i), { target: { value: 'gamma' } });
    fireEvent.change(screen.getByPlaceholderText(/search/i), { target: { value: '' } });
    expect(screen.getAllByTestId('status-badge')).toHaveLength(4);
  });
});

describe('ProofPage — dropdown filters', () => {
  beforeEach(() => jest.clearAllMocks());

  it('filters to only open requirements when Status=open selected', () => {
    setup();
    fireEvent.change(screen.getByRole('combobox', { name: /status/i }), { target: { value: 'open' } });
    const badges = screen.getAllByTestId('status-badge');
    expect(badges.every((b) => b.textContent === 'open')).toBe(true);
    expect(badges).toHaveLength(2);
  });

  it('filters to only critical requirements when Severity=critical selected', () => {
    setup();
    fireEvent.change(screen.getByRole('combobox', { name: /severity/i }), { target: { value: 'critical' } });
    expect(screen.getAllByTestId('status-badge')).toHaveLength(1);
    expect(screen.getByText('Beta')).toBeInTheDocument();
  });

  it('filters by glitch type', () => {
    setup();
    fireEvent.change(screen.getByRole('combobox', { name: /glitch type/i }), { target: { value: 'security' } });
    expect(screen.getAllByTestId('status-badge')).toHaveLength(1);
    expect(screen.getByText('Beta')).toBeInTheDocument();
  });

  it('combines Status and Severity filters with AND logic', () => {
    setup();
    fireEvent.change(screen.getByRole('combobox', { name: /status/i }), { target: { value: 'open' } });
    fireEvent.change(screen.getByRole('combobox', { name: /severity/i }), { target: { value: 'medium' } });
    expect(screen.getAllByTestId('status-badge')).toHaveLength(1);
    expect(screen.getByText('Delta')).toBeInTheDocument();
  });
});

describe('ProofPage — reset filters', () => {
  beforeEach(() => jest.clearAllMocks());

  it('clears all filters when Reset is clicked', () => {
    setup();
    fireEvent.change(screen.getByPlaceholderText(/search/i), { target: { value: 'gamma' } });
    fireEvent.change(screen.getByRole('combobox', { name: /status/i }), { target: { value: 'waived' } });
    fireEvent.click(screen.getByRole('button', { name: /reset/i }));
    expect(screen.getAllByTestId('status-badge')).toHaveLength(4);
  });
});
