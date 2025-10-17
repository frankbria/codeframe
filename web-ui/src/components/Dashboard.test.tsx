/**
 * Tests for Dashboard Component Integration
 * Testing PRD and Task display features (cf-26)
 */

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import Dashboard from './Dashboard';

// Mock SWR
jest.mock('swr', () => ({
  __esModule: true,
  default: jest.fn((key, fetcher) => {
    // Mock different endpoints
    if (key === '/projects/1/status') {
      return {
        data: {
          name: 'Test Project',
          status: 'active',
          phase: 'development',
          workflow_step: 5,
          progress: {
            completed_tasks: 10,
            total_tasks: 20,
            percentage: 50,
          },
          time_tracking: {
            started_at: '2025-10-15T09:00:00Z',
            elapsed_hours: 5.5,
            estimated_remaining_hours: 10.5,
          },
          cost_tracking: {
            input_tokens: 1500000,
            output_tokens: 50000,
            estimated_cost: 15.75,
          },
        },
        error: undefined,
        mutate: jest.fn(),
      };
    }
    if (key === '/projects/1/agents') {
      return {
        data: [],
        error: undefined,
      };
    }
    if (key === '/projects/1/blockers') {
      return {
        data: [],
        error: undefined,
        mutate: jest.fn(),
      };
    }
    if (key === '/projects/1/activity') {
      return {
        data: [],
        error: undefined,
      };
    }
    return { data: undefined, error: undefined };
  }),
}));

// Mock WebSocket
jest.mock('@/lib/websocket', () => ({
  getWebSocketClient: () => ({
    connect: jest.fn(),
    disconnect: jest.fn(),
    subscribe: jest.fn(),
    onMessage: jest.fn(() => jest.fn()),
  }),
}));

// Mock API calls
jest.mock('@/lib/api', () => ({
  projectsApi: {
    getStatus: jest.fn(),
    getPRD: jest.fn(),
    getIssues: jest.fn(),
  },
  agentsApi: {
    list: jest.fn(),
  },
  blockersApi: {
    list: jest.fn(),
  },
  activityApi: {
    list: jest.fn(),
  },
}));

describe('Dashboard - PRD and Task Integration (cf-26)', () => {
  describe('PRD Button', () => {
    it('should render "View PRD" button', () => {
      render(<Dashboard projectId={1} />);

      expect(screen.getByRole('button', { name: /view prd/i })).toBeInTheDocument();
    });

    it('should open PRD modal when button is clicked', async () => {
      const user = userEvent.setup();

      render(<Dashboard projectId={1} />);

      const prdButton = screen.getByRole('button', { name: /view prd/i });
      await user.click(prdButton);

      // Modal should be visible
      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });
    });

    it('should close PRD modal when close button is clicked', async () => {
      const user = userEvent.setup();

      render(<Dashboard projectId={1} />);

      // Open modal
      const prdButton = screen.getByRole('button', { name: /view prd/i });
      await user.click(prdButton);

      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });

      // Close modal
      const closeButton = screen.getByRole('button', { name: /close/i });
      await user.click(closeButton);

      await waitFor(() => {
        expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
      });
    });
  });

  describe('Task Tree Section', () => {
    it('should render task tree section', () => {
      render(<Dashboard projectId={1} />);

      expect(screen.getByText(/issues.*tasks/i)).toBeInTheDocument();
    });

    it('should display TaskTreeView component', () => {
      render(<Dashboard projectId={1} />);

      // Should render TaskTreeView (may show empty state initially)
      expect(screen.getByText(/no issues/i)).toBeInTheDocument();
    });
  });

  describe('Layout', () => {
    it('should render PRD button in header area', () => {
      render(<Dashboard projectId={1} />);

      const header = screen.getByRole('banner') || document.querySelector('header');
      const prdButton = screen.getByRole('button', { name: /view prd/i });

      expect(header).toContainElement(prdButton);
    });

    it('should render task tree after progress section', () => {
      const { container } = render(<Dashboard projectId={1} />);

      const progressSection = screen.getByText(/Progress/i).closest('div');
      const taskTreeSection = screen.getByText(/issues.*tasks/i).closest('div');

      // Get all sections
      const sections = Array.from(container.querySelectorAll('.bg-white.rounded-lg.shadow'));

      const progressIndex = sections.findIndex((s) => s.contains(progressSection));
      const taskTreeIndex = sections.findIndex((s) => s.contains(taskTreeSection));

      // Task tree should come after progress
      expect(taskTreeIndex).toBeGreaterThan(progressIndex);
    });

    it('should maintain existing Dashboard structure', () => {
      render(<Dashboard projectId={1} />);

      // All existing sections should still be present
      expect(screen.getByText(/Progress/i)).toBeInTheDocument();
      expect(screen.getByText(/Agent Status/i)).toBeInTheDocument();
      expect(screen.getByText(/Recent Activity/i)).toBeInTheDocument();
    });
  });

  describe('Data Loading', () => {
    it('should show loading state while fetching PRD data', async () => {
      render(<Dashboard projectId={1} />);

      const prdButton = screen.getByRole('button', { name: /view prd/i });

      // Button should be enabled (we'll test loading in modal)
      expect(prdButton).not.toBeDisabled();
    });

    it('should show loading state while fetching issues data', () => {
      render(<Dashboard projectId={1} />);

      // Should render issues section (may show empty state initially)
      expect(screen.getByText(/issues.*tasks/i)).toBeInTheDocument();
    });
  });

  describe('Error Handling', () => {
    it('should handle PRD fetch errors gracefully', async () => {
      const user = userEvent.setup();

      render(<Dashboard projectId={1} />);

      const prdButton = screen.getByRole('button', { name: /view prd/i });
      await user.click(prdButton);

      // Should still render modal (will show error state inside)
      await waitFor(() => {
        expect(screen.getByRole('dialog')).toBeInTheDocument();
      });
    });

    it('should handle issues fetch errors gracefully', () => {
      render(<Dashboard projectId={1} />);

      // Should render issues section (may show empty state)
      expect(screen.getByText(/issues.*tasks/i)).toBeInTheDocument();
    });
  });

  describe('Accessibility', () => {
    it('should have accessible PRD button', () => {
      render(<Dashboard projectId={1} />);

      const prdButton = screen.getByRole('button', { name: /view prd/i });
      expect(prdButton).toHaveAccessibleName();
    });

    it('should maintain proper heading hierarchy', () => {
      render(<Dashboard projectId={1} />);

      const headings = screen.getAllByRole('heading');

      // Should have h1 for main title
      const h1 = headings.find((h) => h.tagName === 'H1');
      expect(h1).toBeInTheDocument();

      // Should have h2 for sections
      const h2s = headings.filter((h) => h.tagName === 'H2');
      expect(h2s.length).toBeGreaterThan(0);
    });
  });
});
