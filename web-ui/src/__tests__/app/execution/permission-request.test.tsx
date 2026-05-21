/**
 * Verifies the execution landing page requests Notification permission
 * exactly once, only when permission is 'default', and not at all when
 * already granted or denied. (#559 acceptance criterion: "Permission
 * request shown once and respected".)
 */
import { render } from '@testing-library/react';
import ExecutionLandingPage from '@/app/execution/page';

jest.mock('@/lib/workspace-storage', () => ({
  getSelectedWorkspacePath: jest.fn(() => null),
}));
jest.mock('next/navigation', () => ({
  useSearchParams: () => new URLSearchParams(),
  useRouter: () => ({ replace: jest.fn(), push: jest.fn() }),
}));
jest.mock('@/components/execution/BatchExecutionMonitor', () => ({
  BatchExecutionMonitor: () => null,
}));

let currentPermission: NotificationPermission = 'default';
const requestPermissionMock = jest.fn().mockResolvedValue('granted');

function installNotificationStub() {
  const stub = function () {} as unknown as typeof Notification;
  Object.defineProperty(stub, 'permission', { configurable: true, get: () => currentPermission });
  Object.defineProperty(stub, 'requestPermission', { configurable: true, value: requestPermissionMock });
  (global as unknown as { Notification: typeof Notification }).Notification = stub;
}

beforeEach(() => {
  requestPermissionMock.mockClear();
  currentPermission = 'default';
  installNotificationStub();
});

describe('ExecutionLandingPage permission request', () => {
  it('calls Notification.requestPermission once when permission is default', () => {
    render(<ExecutionLandingPage />);
    expect(requestPermissionMock).toHaveBeenCalledTimes(1);
  });

  it('does NOT request permission when already granted', () => {
    currentPermission = 'granted';
    render(<ExecutionLandingPage />);
    expect(requestPermissionMock).not.toHaveBeenCalled();
  });

  it('does NOT request permission when already denied', () => {
    currentPermission = 'denied';
    render(<ExecutionLandingPage />);
    expect(requestPermissionMock).not.toHaveBeenCalled();
  });
});
