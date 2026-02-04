import { render, screen } from '@testing-library/react';
import { QuickActions } from '@/components/workspace/QuickActions';

// Mock next/link
jest.mock('next/link', () => {
  return function MockLink({
    children,
    href,
  }: {
    children: React.ReactNode;
    href: string;
  }) {
    return <a href={href}>{children}</a>;
  };
});

describe('QuickActions', () => {
  it('renders all quick action buttons', () => {
    render(<QuickActions />);

    expect(screen.getByRole('link', { name: /view prd/i })).toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: /manage tasks/i })
    ).toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: /review changes/i })
    ).toBeInTheDocument();
  });

  it('links to correct routes', () => {
    render(<QuickActions />);

    expect(screen.getByRole('link', { name: /view prd/i })).toHaveAttribute(
      'href',
      '/prd'
    );
    expect(screen.getByRole('link', { name: /manage tasks/i })).toHaveAttribute(
      'href',
      '/tasks'
    );
    expect(
      screen.getByRole('link', { name: /review changes/i })
    ).toHaveAttribute('href', '/review');
  });

  it('renders section title', () => {
    render(<QuickActions />);

    expect(screen.getByText('Quick Actions')).toBeInTheDocument();
  });
});
