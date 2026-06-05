/**
 * AppLayout must render the login page bare — without the sidebar shell or
 * pipeline progress bar (issue #336). On every other route it renders the
 * full shell.
 */
import { render, screen } from '@testing-library/react';
import { AppLayout } from '@/components/layout/AppLayout';

let mockPathname = '/tasks';
jest.mock('next/navigation', () => ({
  usePathname: () => mockPathname,
}));

jest.mock('@/components/layout/AppSidebar', () => ({
  AppSidebar: () => <aside data-testid="app-sidebar" />,
}));
jest.mock('@/components/layout/PipelineProgressBar', () => ({
  PipelineProgressBar: () => <div data-testid="pipeline-bar" />,
}));

describe('AppLayout', () => {
  it('renders the sidebar shell on a normal route', () => {
    mockPathname = '/tasks';
    render(
      <AppLayout>
        <div data-testid="child">content</div>
      </AppLayout>
    );
    expect(screen.getByTestId('app-sidebar')).toBeInTheDocument();
    expect(screen.getByTestId('pipeline-bar')).toBeInTheDocument();
    expect(screen.getByTestId('child')).toBeInTheDocument();
  });

  it('renders bare (no sidebar/pipeline bar) on /login', () => {
    mockPathname = '/login';
    render(
      <AppLayout>
        <div data-testid="child">login</div>
      </AppLayout>
    );
    expect(screen.queryByTestId('app-sidebar')).not.toBeInTheDocument();
    expect(screen.queryByTestId('pipeline-bar')).not.toBeInTheDocument();
    expect(screen.getByTestId('child')).toBeInTheDocument();
  });
});
