import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { TechStackConfirmDialog } from '@/components/workspace/TechStackConfirmDialog';

describe('TechStackConfirmDialog', () => {
  const onConfirm = jest.fn();
  const onCancel = jest.fn();

  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('when closed', () => {
    it('renders nothing', () => {
      const { container } = render(
        <TechStackConfirmDialog
          open={false}
          detectedStack="Python with uv"
          onConfirm={onConfirm}
          onCancel={onCancel}
        />
      );
      expect(container.firstChild).toBeNull();
    });
  });

  describe('detection success', () => {
    beforeEach(() => {
      render(
        <TechStackConfirmDialog
          open={true}
          detectedStack="Python with uv, pytest, ruff"
          onConfirm={onConfirm}
          onCancel={onCancel}
        />
      );
    });

    it('shows detected stack', () => {
      expect(screen.getByText('Python with uv, pytest, ruff')).toBeInTheDocument();
    });

    it('shows confirm and edit buttons', () => {
      expect(screen.getByRole('button', { name: /confirm/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /edit/i })).toBeInTheDocument();
    });

    it('calls onConfirm with detected stack on confirm click', () => {
      fireEvent.click(screen.getByRole('button', { name: /confirm/i }));
      expect(onConfirm).toHaveBeenCalledWith('Python with uv, pytest, ruff');
    });

    it('calls onCancel when cancel/close is triggered', () => {
      fireEvent.click(screen.getByRole('button', { name: /cancel/i }));
      expect(onCancel).toHaveBeenCalled();
    });
  });

  describe('edit mode', () => {
    beforeEach(() => {
      render(
        <TechStackConfirmDialog
          open={true}
          detectedStack="Python with uv"
          onConfirm={onConfirm}
          onCancel={onCancel}
        />
      );
      fireEvent.click(screen.getByRole('button', { name: /edit/i }));
    });

    it('shows textarea pre-filled with detected stack', () => {
      const textarea = screen.getByRole('textbox');
      expect(textarea).toHaveValue('Python with uv');
    });

    it('calls onConfirm with edited value', () => {
      const textarea = screen.getByRole('textbox');
      fireEvent.change(textarea, { target: { value: 'TypeScript with Next.js' } });
      fireEvent.click(screen.getByRole('button', { name: /save/i }));
      expect(onConfirm).toHaveBeenCalledWith('TypeScript with Next.js');
    });
  });

  describe('detection failure', () => {
    beforeEach(() => {
      render(
        <TechStackConfirmDialog
          open={true}
          detectedStack={null}
          onConfirm={onConfirm}
          onCancel={onCancel}
        />
      );
    });

    it('shows failure message', () => {
      expect(screen.getByText(/could not auto-detect/i)).toBeInTheDocument();
    });

    it('shows textarea for manual entry', () => {
      expect(screen.getByRole('textbox')).toBeInTheDocument();
    });

    it('calls onConfirm with entered value', () => {
      const textarea = screen.getByRole('textbox');
      fireEvent.change(textarea, { target: { value: 'Rust with cargo' } });
      fireEvent.click(screen.getByRole('button', { name: /save/i }));
      expect(onConfirm).toHaveBeenCalledWith('Rust with cargo');
    });

    it('save button is disabled when textarea is empty', () => {
      const saveBtn = screen.getByRole('button', { name: /save/i });
      expect(saveBtn).toBeDisabled();
    });
  });
});
