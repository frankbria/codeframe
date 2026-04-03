import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import useSWR from 'swr';
import ProofDetailPage from '@/app/proof/[req_id]/page';
import * as storage from '@/lib/workspace-storage';
import type { ProofEvidence, ProofRequirement, ProofEvidenceSortCol, SortDir } from '@/types';

// ── Mocks ────────────────────────────────────────────────────────────────

jest.mock('swr');
jest.mock('next/navigation', () => ({
  useParams: () => ({ req_id: 'REQ-001' }),
}));
jest.mock('@/lib/workspace-storage', () => ({
  getSelectedWorkspacePath: jest.fn(),
}));
jest.mock('@/lib/api', () => ({
  proofApi: {
    getRequirement: jest.fn(),
    getEvidence: jest.fn(),
    waiveRequirement: jest.fn(),
  },
}));
jest.mock('@/components/proof', () => ({
  ProofStatusBadge: ({ status }: { status: string }) => <span data-testid="status-badge">{status}</span>,
  WaiveDialog: () => null,
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

const EVIDENCE: ProofEvidence[] = [
  { req_id: 'REQ-001', gate: 'lint',   satisfied: true,  artifact_path: '/a/lint.log',  artifact_checksum: '', timestamp: '2026-01-03T10:00:00Z', run_id: 'run-001' },
  { req_id: 'REQ-001', gate: 'test',   satisfied: false, artifact_path: '/a/test.log',  artifact_checksum: '', timestamp: '2026-01-01T10:00:00Z', run_id: 'run-002' },
  { req_id: 'REQ-001', gate: 'build',  satisfied: true,  artifact_path: '/b/build.log', artifact_checksum: '', timestamp: '2026-01-02T10:00:00Z', run_id: 'run-003' },
  { req_id: 'REQ-001', gate: 'lint',   satisfied: false, artifact_path: '/a/lint2.log', artifact_checksum: '', timestamp: '2026-01-04T10:00:00Z', run_id: 'run-004' },
];

const REQ: ProofRequirement = {
  id: 'REQ-001',
  title: 'Test req',
  description: 'desc',
  severity: 'medium',
  source: 'manual',
  status: 'open',
  glitch_type: null,
  obligations: [],
  evidence_rules: [],
  waiver: null,
  created_at: '2026-01-01T00:00:00Z',
  satisfied_at: null,
  created_by: 'user',
  source_issue: null,
  related_reqs: [],
};

function setup(evidence: ProofEvidence[] = EVIDENCE) {
  mockGetWorkspace.mockReturnValue(WORKSPACE);
  mockUseSWR.mockImplementation((key: unknown) => {
    if (!key) {
      return { data: undefined, error: undefined, isLoading: false, mutate: jest.fn() } as unknown as ReturnType<typeof useSWR>;
    }
    const k = String(key);
    if (k.includes('/evidence')) {
      return { data: evidence, error: undefined, isLoading: false, mutate: jest.fn() } as unknown as ReturnType<typeof useSWR>;
    }
    return { data: REQ, error: undefined, isLoading: false, mutate: jest.fn() } as unknown as ReturnType<typeof useSWR>;
  });
  render(<ProofDetailPage />);
}

function evidenceRows() {
  // Each evidence row has exactly 5 cells; skip header row
  const allRows = screen.getAllByRole('row');
  return allRows.filter((r) => r.querySelectorAll('td').length === 5);
}

// ── Tests ─────────────────────────────────────────────────────────────────

// Clear mocks and sessionStorage before each test to prevent filter state leaking
beforeEach(() => {
  jest.clearAllMocks();
  sessionStorage.clear();
});

describe('ProofDetailPage — evidence filter controls', () => {
  beforeEach(() => jest.clearAllMocks());

  it('renders Gate filter dropdown', () => {
    setup();
    expect(screen.getByRole('combobox', { name: /gate/i })).toBeInTheDocument();
  });

  it('renders Result filter dropdown', () => {
    setup();
    expect(screen.getByRole('combobox', { name: /result/i })).toBeInTheDocument();
  });

  it('renders search input for run ID / artifact', () => {
    setup();
    expect(screen.getByPlaceholderText(/run id|artifact/i)).toBeInTheDocument();
  });

  it('does not render Reset button when no filters are active', () => {
    setup();
    expect(screen.queryByRole('button', { name: /reset/i })).not.toBeInTheDocument();
  });

  it('renders Reset button when gate filter is set', () => {
    setup();
    fireEvent.change(screen.getByRole('combobox', { name: /gate/i }), { target: { value: 'lint' } });
    expect(screen.getByRole('button', { name: /reset/i })).toBeInTheDocument();
  });

  it('renders Reset button when search is non-empty', () => {
    setup();
    fireEvent.change(screen.getByPlaceholderText(/run id|artifact/i), { target: { value: 'foo' } });
    expect(screen.getByRole('button', { name: /reset/i })).toBeInTheDocument();
  });
});

describe('ProofDetailPage — default sort (timestamp descending)', () => {
  beforeEach(() => jest.clearAllMocks());

  it('shows most recent entry first by default', () => {
    setup();
    const rows = evidenceRows();
    const firstRunId = rows[0].querySelectorAll('td')[2].textContent?.trim();
    // run-004 has timestamp 2026-01-04 — most recent
    expect(firstRunId).toBe('run-004');
  });
});

describe('ProofDetailPage — gate filter', () => {
  beforeEach(() => jest.clearAllMocks());

  it('filters evidence to only matching gate', () => {
    setup();
    fireEvent.change(screen.getByRole('combobox', { name: /gate/i }), { target: { value: 'lint' } });
    const rows = evidenceRows();
    expect(rows).toHaveLength(2);
    rows.forEach((r) => expect(r.querySelectorAll('td')[0].textContent).toBe('lint'));
  });

  it('shows all rows when gate reset to empty', () => {
    setup();
    fireEvent.change(screen.getByRole('combobox', { name: /gate/i }), { target: { value: 'lint' } });
    fireEvent.change(screen.getByRole('combobox', { name: /gate/i }), { target: { value: '' } });
    expect(evidenceRows()).toHaveLength(4);
  });
});

describe('ProofDetailPage — result filter', () => {
  beforeEach(() => jest.clearAllMocks());

  it('filters to only passing evidence when result=pass', () => {
    setup();
    fireEvent.change(screen.getByRole('combobox', { name: /result/i }), { target: { value: 'pass' } });
    const rows = evidenceRows();
    expect(rows).toHaveLength(2);
    rows.forEach((r) => expect(r.querySelectorAll('td')[1].textContent?.trim()).toBe('pass'));
  });

  it('filters to only failing evidence when result=fail', () => {
    setup();
    fireEvent.change(screen.getByRole('combobox', { name: /result/i }), { target: { value: 'fail' } });
    const rows = evidenceRows();
    expect(rows).toHaveLength(2);
    rows.forEach((r) => expect(r.querySelectorAll('td')[1].textContent?.trim()).toBe('fail'));
  });
});

describe('ProofDetailPage — search filter', () => {
  beforeEach(() => jest.clearAllMocks());

  it('filters by run_id substring', () => {
    setup();
    fireEvent.change(screen.getByPlaceholderText(/run id|artifact/i), { target: { value: 'run-002' } });
    expect(evidenceRows()).toHaveLength(1);
  });

  it('filters by artifact_path substring (case-insensitive)', () => {
    setup();
    fireEvent.change(screen.getByPlaceholderText(/run id|artifact/i), { target: { value: '/b/' } });
    expect(evidenceRows()).toHaveLength(1);
  });

  it('shows all rows when search is cleared', () => {
    setup();
    fireEvent.change(screen.getByPlaceholderText(/run id|artifact/i), { target: { value: 'run-001' } });
    fireEvent.change(screen.getByPlaceholderText(/run id|artifact/i), { target: { value: '' } });
    expect(evidenceRows()).toHaveLength(4);
  });
});

describe('ProofDetailPage — sortable columns', () => {
  beforeEach(() => jest.clearAllMocks());

  it('renders sort buttons for Gate, Result, Run ID, Timestamp, Artifact', () => {
    setup();
    expect(screen.getByRole('button', { name: /sort by gate/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /sort by result/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /sort by run id/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /sort by timestamp/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /sort by artifact/i })).toBeInTheDocument();
  });

  it('sorts by gate ascending on first click', () => {
    setup();
    fireEvent.click(screen.getByRole('button', { name: /sort by gate/i }));
    const rows = evidenceRows();
    const gates = rows.map((r) => r.querySelectorAll('td')[0].textContent?.trim());
    expect(gates[0]).toBe('build');
  });

  it('sorts by gate descending on second click', () => {
    setup();
    fireEvent.click(screen.getByRole('button', { name: /sort by gate/i }));
    fireEvent.click(screen.getByRole('button', { name: /sort by gate/i }));
    const rows = evidenceRows();
    const gates = rows.map((r) => r.querySelectorAll('td')[0].textContent?.trim());
    expect(gates[0]).toBe('test');
  });

  it('sets aria-sort on the sorted th', () => {
    setup();
    fireEvent.click(screen.getByRole('button', { name: /sort by gate/i }));
    const th = screen.getByRole('button', { name: /sort by gate/i }).closest('th');
    expect(th).toHaveAttribute('aria-sort', 'ascending');
  });

  it('sorts timestamp ascending when clicked (overriding default desc)', () => {
    setup();
    fireEvent.click(screen.getByRole('button', { name: /sort by timestamp/i }));
    const rows = evidenceRows();
    const firstRunId = rows[0].querySelectorAll('td')[2].textContent?.trim();
    // run-002 is oldest (2026-01-01)
    expect(firstRunId).toBe('run-002');
  });
});

describe('ProofDetailPage — reset filters', () => {
  beforeEach(() => jest.clearAllMocks());

  it('clears all filters when Reset is clicked', () => {
    setup();
    fireEvent.change(screen.getByRole('combobox', { name: /gate/i }), { target: { value: 'lint' } });
    fireEvent.change(screen.getByRole('combobox', { name: /result/i }), { target: { value: 'fail' } });
    fireEvent.change(screen.getByPlaceholderText(/run id|artifact/i), { target: { value: 'run' } });
    fireEvent.click(screen.getByRole('button', { name: /reset/i }));
    expect(evidenceRows()).toHaveLength(4);
    expect(screen.queryByRole('button', { name: /reset/i })).not.toBeInTheDocument();
  });
});

describe('ProofDetailPage — combined filters', () => {
  beforeEach(() => jest.clearAllMocks());

  it('combines gate and result with AND logic', () => {
    setup();
    fireEvent.change(screen.getByRole('combobox', { name: /gate/i }), { target: { value: 'lint' } });
    fireEvent.change(screen.getByRole('combobox', { name: /result/i }), { target: { value: 'pass' } });
    expect(evidenceRows()).toHaveLength(1);
  });
});
