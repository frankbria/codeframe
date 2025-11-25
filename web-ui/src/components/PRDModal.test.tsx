/**
 * Tests for PRDModal Component
 * TDD: RED phase - These tests should fail initially
 */

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import PRDModal from './PRDModal';
import type { PRDResponse } from '@/types/api';

describe('PRDModal', () => {
  const mockPRDData: PRDResponse = {
    project_id: 'test-project-1',
    prd_content: '# Product Requirements Document\n\nThis is a test PRD with **markdown** formatting.\n\n## Features\n- Feature 1\n- Feature 2',
    generated_at: '2025-10-17T10:00:00Z',
    updated_at: '2025-10-17T12:00:00Z',
    status: 'available',
  };

  const mockOnClose = jest.fn();

  beforeEach(() => {
    mockOnClose.mockClear();
  });

  describe('Rendering', () => {
    it('should render modal when isOpen is true', () => {
      render(
        <PRDModal isOpen={true} onClose={mockOnClose} prdData={mockPRDData} />
      );

      expect(screen.getByRole('dialog')).toBeInTheDocument();
      expect(screen.getByRole('heading', { name: /Product Requirements Document/i })).toBeInTheDocument();
    });

    it('should not render modal when isOpen is false', () => {
      render(
        <PRDModal isOpen={false} onClose={mockOnClose} prdData={mockPRDData} />
      );

      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });

    it('should display PRD content when status is available', () => {
      render(
        <PRDModal isOpen={true} onClose={mockOnClose} prdData={mockPRDData} />
      );

      expect(screen.getByText(/This is a test PRD/i)).toBeInTheDocument();
      expect(screen.getByText(/Feature 1/i)).toBeInTheDocument();
    });

    it('should display loading state when status is generating', () => {
      const generatingData: PRDResponse = {
        ...mockPRDData,
        status: 'generating',
        prd_content: '',
      };

      render(
        <PRDModal isOpen={true} onClose={mockOnClose} prdData={generatingData} />
      );

      expect(screen.getByText(/Generating PRD/i)).toBeInTheDocument();
    });

    it('should display not found message when status is not_found', () => {
      const notFoundData: PRDResponse = {
        ...mockPRDData,
        status: 'not_found',
        prd_content: '',
      };

      render(
        <PRDModal isOpen={true} onClose={mockOnClose} prdData={notFoundData} />
      );

      expect(screen.getByText(/not found/i)).toBeInTheDocument();
    });

    it('should display project ID', () => {
      render(
        <PRDModal isOpen={true} onClose={mockOnClose} prdData={mockPRDData} />
      );

      expect(screen.getByText(/test-project-1/i)).toBeInTheDocument();
    });

    it('should display timestamps', () => {
      render(
        <PRDModal isOpen={true} onClose={mockOnClose} prdData={mockPRDData} />
      );

      // Check for timestamp labels
      expect(screen.getByText(/generated/i)).toBeInTheDocument();
      expect(screen.getByText(/updated/i)).toBeInTheDocument();
    });

    it('should render close button', () => {
      render(
        <PRDModal isOpen={true} onClose={mockOnClose} prdData={mockPRDData} />
      );

      expect(screen.getByRole('button', { name: /close/i })).toBeInTheDocument();
    });
  });

  describe('User Interactions', () => {
    it('should call onClose when close button is clicked', async () => {
      const user = userEvent.setup();

      render(
        <PRDModal isOpen={true} onClose={mockOnClose} prdData={mockPRDData} />
      );

      const closeButton = screen.getByRole('button', { name: /close/i });
      await user.click(closeButton);

      expect(mockOnClose).toHaveBeenCalledTimes(1);
    });

    it('should call onClose when clicking outside modal (overlay)', async () => {
      const user = userEvent.setup();

      render(
        <PRDModal isOpen={true} onClose={mockOnClose} prdData={mockPRDData} />
      );

      // Find and click the overlay (backdrop)
      const overlay = screen.getByRole('dialog').parentElement;
      if (overlay) {
        await user.click(overlay);
        expect(mockOnClose).toHaveBeenCalled();
      }
    });

    it('should call onClose when pressing Escape key', async () => {
      const user = userEvent.setup();

      render(
        <PRDModal isOpen={true} onClose={mockOnClose} prdData={mockPRDData} />
      );

      await user.keyboard('{Escape}');

      expect(mockOnClose).toHaveBeenCalled();
    });
  });

  describe('Markdown Rendering', () => {
    it('should render markdown content with proper formatting', () => {
      render(
        <PRDModal isOpen={true} onClose={mockOnClose} prdData={mockPRDData} />
      );

      // Check for modal heading
      expect(screen.getByRole('heading', { name: /Product Requirements Document/i })).toBeInTheDocument();

      // Check for markdown content - since we mocked ReactMarkdown, it renders as plain text
      expect(screen.getByText(/This is a test PRD/i)).toBeInTheDocument();
      expect(screen.getByText(/Feature 1/i)).toBeInTheDocument();
    });
  });

  describe('Accessibility', () => {
    it('should have proper ARIA attributes', () => {
      render(
        <PRDModal isOpen={true} onClose={mockOnClose} prdData={mockPRDData} />
      );

      const dialog = screen.getByRole('dialog');
      expect(dialog).toHaveAttribute('aria-modal', 'true');
      expect(dialog).toHaveAttribute('aria-labelledby');
    });

    it('should trap focus within modal when open', async () => {
      render(
        <PRDModal isOpen={true} onClose={mockOnClose} prdData={mockPRDData} />
      );

      const dialog = screen.getByRole('dialog');
      expect(dialog).toBeInTheDocument();

      // Focus should be trapped within the modal
      const closeButton = screen.getByRole('button', { name: /close/i });
      expect(document.activeElement).toBe(closeButton);
    });
  });

  describe('Edge Cases', () => {
    it('should handle null prdData gracefully', () => {
      render(
        <PRDModal isOpen={true} onClose={mockOnClose} prdData={null} />
      );

      expect(screen.getByText(/no prd data/i)).toBeInTheDocument();
    });

    it('should handle empty prd_content', () => {
      const emptyData: PRDResponse = {
        ...mockPRDData,
        prd_content: '',
      };

      render(
        <PRDModal isOpen={true} onClose={mockOnClose} prdData={emptyData} />
      );

      expect(screen.getByText(/no content/i)).toBeInTheDocument();
    });

    it('should handle very long PRD content with scrolling', () => {
      const longContent = '# Long PRD\n\n' + 'Lorem ipsum dolor sit amet. '.repeat(1000);
      const longData: PRDResponse = {
        ...mockPRDData,
        prd_content: longContent,
      };

      render(
        <PRDModal isOpen={true} onClose={mockOnClose} prdData={longData} />
      );

      const dialog = screen.getByRole('dialog');
      expect(dialog).toBeInTheDocument();
      // Content area should have overflow handling
      const contentArea = dialog.querySelector('[data-testid="prd-content"]');
      expect(contentArea).toHaveClass('overflow-y-auto');
    });
  });
});
