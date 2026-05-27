import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { PRDHeader } from '@/components/prd/PRDHeader';
import type { PrdResponse } from '@/types';

const fakePrd: PrdResponse = {
  id: 'prd-1',
  workspace_id: 'ws-1',
  title: 'My PRD',
  content: '# Overview',
  metadata: {},
  created_at: '2026-01-01T00:00:00Z',
  version: 1,
  parent_id: null,
  change_summary: null,
  chain_id: 'chain-1',
};

const noop = () => {};

function renderHeader(overrides: Partial<React.ComponentProps<typeof PRDHeader>> = {}) {
  return render(
    <PRDHeader
      prd={fakePrd}
      onUploadPrd={noop}
      onStartDiscovery={noop}
      onGenerateTasks={noop}
      {...overrides}
    />
  );
}

describe('PRDHeader — Stress Test button', () => {
  it('is not rendered when onStressTest is not provided', () => {
    renderHeader();
    expect(
      screen.queryByRole('button', { name: /stress test/i })
    ).not.toBeInTheDocument();
  });

  it('is visible and enabled when a PRD exists', () => {
    renderHeader({ onStressTest: noop });
    const button = screen.getByRole('button', { name: /stress test/i });
    expect(button).toBeInTheDocument();
    expect(button).toBeEnabled();
  });

  it('is disabled when no PRD exists', () => {
    renderHeader({ prd: null, onStressTest: noop });
    expect(screen.getByRole('button', { name: /stress test/i })).toBeDisabled();
  });

  it('calls onStressTest when clicked', async () => {
    const onStressTest = jest.fn();
    renderHeader({ onStressTest });
    await userEvent.click(screen.getByRole('button', { name: /stress test/i }));
    expect(onStressTest).toHaveBeenCalledTimes(1);
  });
});
