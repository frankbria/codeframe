import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { GateEvidencePanel } from '@/components/proof/GateEvidencePanel';
import type { ProofEvidenceWithContent } from '@/types';

function makeEvidence(overrides: Partial<ProofEvidenceWithContent> = {}): ProofEvidenceWithContent {
  return {
    req_id: 'REQ-001',
    gate: 'unit',
    satisfied: true,
    artifact_path: '/tmp/REQ-001_unit_abc.txt',
    artifact_checksum: 'abc123',
    timestamp: '2026-04-09T12:00:00Z',
    run_id: 'abc12345',
    artifact_text: 'test output line 1\ntest output line 2',
    ...overrides,
  };
}

describe('GateEvidencePanel', () => {
  it('renders nothing for empty evidence', () => {
    const { container } = render(<GateEvidencePanel evidence={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders a row per evidence item', () => {
    const evidence = [
      makeEvidence({ gate: 'unit', satisfied: true }),
      makeEvidence({ gate: 'sec', satisfied: false }),
    ];
    render(<GateEvidencePanel evidence={evidence} />);
    expect(screen.getByText('unit')).toBeInTheDocument();
    expect(screen.getByText('sec')).toBeInTheDocument();
  });

  it('shows pass badge for satisfied evidence', () => {
    render(<GateEvidencePanel evidence={[makeEvidence({ satisfied: true })]} />);
    expect(screen.getByText('pass')).toBeInTheDocument();
  });

  it('shows fail badge for unsatisfied evidence', () => {
    render(<GateEvidencePanel evidence={[makeEvidence({ satisfied: false })]} />);
    expect(screen.getByText('fail')).toBeInTheDocument();
  });

  it('shows "cannot verify" pill for unverifiable evidence', () => {
    render(<GateEvidencePanel evidence={[makeEvidence({ gate: 'e2e', satisfied: false, status: 'unverifiable' })]} />);
    expect(screen.getByText('cannot verify')).toBeInTheDocument();
    expect(screen.queryByText('fail')).not.toBeInTheDocument();
  });

  it('shows pass pill when status is passed', () => {
    render(<GateEvidencePanel evidence={[makeEvidence({ satisfied: true, status: 'passed' })]} />);
    expect(screen.getByText('pass')).toBeInTheDocument();
  });

  it('falls back to satisfied bool for legacy evidence without status', () => {
    render(<GateEvidencePanel evidence={[makeEvidence({ satisfied: false, status: null })]} />);
    expect(screen.getByText('fail')).toBeInTheDocument();
    expect(screen.queryByText('cannot verify')).not.toBeInTheDocument();
  });

  it('expands to show artifact text on click', () => {
    const ev = makeEvidence({ artifact_text: 'hello output' });
    render(<GateEvidencePanel evidence={[ev]} />);
    // Artifact text should not be visible before click
    expect(screen.queryByText('hello output')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /unit/i }));
    expect(screen.getByText('hello output')).toBeInTheDocument();
  });

  it('shows "No output captured" when artifact_text is null', () => {
    const ev = makeEvidence({ artifact_text: null });
    render(<GateEvidencePanel evidence={[ev]} />);
    fireEvent.click(screen.getByRole('button', { name: /unit/i }));
    expect(screen.getByText('No output captured')).toBeInTheDocument();
  });

  it('shows "Show full output" toggle when text exceeds 200 lines', () => {
    const longText = Array.from({ length: 250 }, (_, i) => `line ${i + 1}`).join('\n');
    const ev = makeEvidence({ artifact_text: longText });
    render(<GateEvidencePanel evidence={[ev]} />);
    fireEvent.click(screen.getByRole('button', { name: /unit/i }));
    expect(screen.getByText('Show full output')).toBeInTheDocument();
  });

  it('does not show "Show full output" for short text', () => {
    const ev = makeEvidence({ artifact_text: 'short output' });
    render(<GateEvidencePanel evidence={[ev]} />);
    fireEvent.click(screen.getByRole('button', { name: /unit/i }));
    expect(screen.queryByText('Show full output')).not.toBeInTheDocument();
  });
});

describe('tampered evidence (#952)', () => {
  const tampered = {
    req_id: 'REQ-1',
    gate: 'unit',
    // The backend downgrades an unverified record, so a client that ignores
    // `verified` still never renders it green.
    satisfied: false,
    status: 'unverifiable' as const,
    artifact_path: '/w/a.txt',
    artifact_checksum: 'abc',
    timestamp: '2026-01-01T00:00:00Z',
    run_id: 'run-1',
    verified: false,
    tamper_detail: 'does not match its recorded checksum',
    artifact_text: null,
  };

  it('shows a tampered badge rather than pass or cannot-verify', () => {
    render(<GateEvidencePanel evidence={[tampered]} />);
    expect(screen.getByText('tampered')).toBeInTheDocument();
    expect(screen.queryByText('pass')).not.toBeInTheDocument();
    expect(screen.queryByText('cannot verify')).not.toBeInTheDocument();
  });

  it('explains why the artifact contents are withheld', async () => {
    render(<GateEvidencePanel evidence={[tampered]} />);
    fireEvent.click(screen.getByRole('button', { expanded: false }));
    expect(
      screen.getByText(/does not match the checksum recorded with this evidence/i)
    ).toBeInTheDocument();
  });

  it('leaves verified evidence rendering as a pass', () => {
    render(
      <GateEvidencePanel
        evidence={[{ ...tampered, satisfied: true, status: 'passed', verified: true, tamper_detail: null }]}
      />
    );
    expect(screen.getByText('pass')).toBeInTheDocument();
    expect(screen.queryByText('tampered')).not.toBeInTheDocument();
  });
});
