import React from 'react';
import { render, screen } from '@testing-library/react';
import { GateRunBanner } from '@/components/proof/GateRunBanner';

describe('GateRunBanner', () => {
  it('shows the green all-passed banner when passed and nothing unverifiable', () => {
    render(<GateRunBanner passed message="done" onRetry={() => {}} />);
    expect(screen.getByText('All gates passed')).toBeInTheDocument();
  });

  it('shows the red failed banner when not passed', () => {
    render(<GateRunBanner passed={false} message="boom" onRetry={() => {}} />);
    expect(screen.getByText('Some gates failed')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
  });

  it('shows an amber "could not be verified" banner when passed but gates were unverifiable', () => {
    render(<GateRunBanner passed message="done" unverifiableCount={2} onRetry={() => {}} />);
    expect(screen.getByText(/could not be verified/i)).toBeInTheDocument();
    expect(screen.getByText(/2 gate/i)).toBeInTheDocument();
    // Not treated as a failure.
    expect(screen.queryByText('Some gates failed')).not.toBeInTheDocument();
  });
});
