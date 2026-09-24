/**
 * KeySlot admin gating (#1255). Storing and removing credentials is
 * admin-only on the server (#717); a non-admin is told so up front instead of
 * typing a key and getting a 403 toast. Verify stays available — it is not
 * admin-guarded.
 */
import { render, screen, fireEvent } from '@testing-library/react';
import { KeySlot } from '@/components/settings/KeySlot';
import type { KeyStatusResponse } from '@/types';

jest.mock('@/lib/api', () => ({
  settingsApi: { storeKey: jest.fn(), verifyKey: jest.fn(), removeKey: jest.fn() },
}));
jest.mock('sonner', () => ({ toast: { success: jest.fn(), error: jest.fn() } }));
jest.mock('@/hooks/useAdminDenied', () => ({ useAdminDenied: jest.fn(() => false) }));

import { useAdminDenied } from '@/hooks/useAdminDenied';
const mockAdminDenied = useAdminDenied as jest.MockedFunction<typeof useAdminDenied>;

const STORED = {
  provider: 'LLM_ANTHROPIC',
  stored: true,
  source: 'stored',
  last_four: 'abcd',
} as unknown as KeyStatusResponse;

function renderSlot() {
  render(
    <KeySlot provider="LLM_ANTHROPIC" displayName="Anthropic" status={STORED} onChanged={jest.fn()} />
  );
  fireEvent.change(screen.getByLabelText('Anthropic'), { target: { value: 'sk-ant-x' } });
}

beforeEach(() => mockAdminDenied.mockReturnValue(false));

it('disables Save and Remove for a non-admin and says why', () => {
  mockAdminDenied.mockReturnValue(true);
  renderSlot();

  expect(screen.getByRole('button', { name: /save/i })).toBeDisabled();
  expect(screen.getByRole('button', { name: /remove/i })).toBeDisabled();
  expect(screen.getByRole('button', { name: /verify/i })).toBeEnabled();
  expect(screen.getByText(/requires an admin account/i)).toBeInTheDocument();
});

it('leaves Save and Remove enabled for an admin', () => {
  renderSlot();

  expect(screen.getByRole('button', { name: /save/i })).toBeEnabled();
  expect(screen.getByRole('button', { name: /remove/i })).toBeEnabled();
  expect(screen.queryByText(/requires an admin account/i)).not.toBeInTheDocument();
});
