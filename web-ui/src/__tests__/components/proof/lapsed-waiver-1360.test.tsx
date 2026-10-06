/**
 * A lapsed waiver is not shown as plainly "waived" (#1360). The merge gate
 * blocks on it (#1276), so "0 open, 1 waived" contradicted the refusal.
 */
import React from 'react';
import { render, screen } from '@testing-library/react';
import useSWR from 'swr';
import { ProofStatusBadge } from '@/components/proof/ProofStatusBadge';
import { ProofStatusWidget } from '@/components/proof/ProofStatusWidget';

jest.mock('swr');
jest.mock('next/link', () => {
  const MockLink = ({ href, children }: { href: string; children: React.ReactNode }) => <a href={href}>{children}</a>;
  MockLink.displayName = 'MockLink';
  return MockLink;
});

const mockUseSWR = useSWR as jest.MockedFunction<typeof useSWR>;

it('the badge says the waiver expired instead of "waived"', () => {
  render(<ProofStatusBadge status="waived" waiverExpired />);
  expect(screen.getByText('waiver expired')).toBeInTheDocument();
  expect(screen.queryByText('waived')).not.toBeInTheDocument();
});

it('a live waiver still reads as waived', () => {
  render(<ProofStatusBadge status="waived" />);
  expect(screen.getByText('waived')).toBeInTheDocument();
});

it('the dashboard widget counts lapsed waivers separately', () => {
  mockUseSWR.mockReturnValue({
    data: { total: 2, open: 0, satisfied: 0, waived: 1, waiver_expired: 1, requirements: [] },
    error: undefined,
    isLoading: false,
  } as unknown as ReturnType<typeof useSWR>);
  render(<ProofStatusWidget workspacePath="/ws" />);
  expect(screen.getByText('1 waived')).toBeInTheDocument();
  expect(screen.getByText('1 waiver expired')).toBeInTheDocument();
});
