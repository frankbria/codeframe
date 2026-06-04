import React from 'react';
import { render, screen } from '@testing-library/react';

import { GitHubIssueBadge } from '@/components/tasks/GitHubIssueBadge';

describe('GitHubIssueBadge', () => {
  it('renders the issue number and links to the issue', () => {
    render(
      <GitHubIssueBadge
        issueNumber={42}
        issueUrl="https://github.com/acme/app/issues/42"
      />
    );
    const link = screen.getByRole('link', {
      name: /imported from github issue #42/i,
    });
    expect(link).toHaveAttribute('href', 'https://github.com/acme/app/issues/42');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', expect.stringContaining('noopener'));
    expect(screen.getByText(/Imported from GitHub #42/)).toBeInTheDocument();
  });

  it('does not propagate clicks to parent handlers', () => {
    const parentClick = jest.fn();
    render(
      <div onClick={parentClick}>
        <GitHubIssueBadge issueNumber={7} issueUrl="https://example.com/7" />
      </div>
    );
    screen.getByRole('link').click();
    expect(parentClick).not.toHaveBeenCalled();
  });
});
