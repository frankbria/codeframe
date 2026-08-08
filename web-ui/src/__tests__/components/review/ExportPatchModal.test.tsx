/**
 * ExportPatchModal behavioural coverage (issue #964).
 *
 * Both export routes have real side effects the user cannot verify from the
 * UI — a clipboard write and a Blob download — and neither was covered. The
 * clipboard path also has a non-HTTPS fallback that had never been exercised.
 */
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ExportPatchModal } from '@/components/review/ExportPatchModal';

const PATCH = 'diff --git a/x b/x\n+added line\n';

function setup(overrides: Record<string, unknown> = {}) {
  const onClose = jest.fn();
  render(
    <ExportPatchModal
      open
      onClose={onClose}
      patchContent={PATCH}
      filename="changes.patch"
      {...overrides}
    />
  );
  return { onClose };
}

describe('ExportPatchModal — rendering', () => {
  it('shows the filename and the patch body', () => {
    setup();
    expect(screen.getByText('changes.patch')).toBeInTheDocument();
    // getByDisplayValue normalises whitespace, which drops the patch's
    // trailing newline — compare the raw value instead.
    expect((screen.getByRole('textbox') as HTMLTextAreaElement).value).toBe(PATCH);
  });

  it('renders nothing when closed', () => {
    setup({ open: false });
    expect(screen.queryByText('changes.patch')).not.toBeInTheDocument();
  });

  it('does not let the patch be edited', () => {
    setup();
    expect(screen.getByRole('textbox')).toHaveAttribute('readonly');
  });
});

describe('ExportPatchModal — copy to clipboard', () => {
  afterEach(() => {
    jest.useRealTimers();
  });

  it('writes the patch to the clipboard and confirms', async () => {
    const writeText = jest.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });

    setup();
    await userEvent.click(screen.getByRole('button', { name: /copy to clipboard/i }));

    expect(writeText).toHaveBeenCalledWith(PATCH);
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /copied/i })).toBeInTheDocument()
    );
  });

  it('falls back to execCommand when the clipboard API is unavailable', async () => {
    // Non-HTTPS contexts reject clipboard writes; the patch must still copy.
    Object.assign(navigator, {
      clipboard: { writeText: jest.fn().mockRejectedValue(new Error('insecure')) },
    });
    const execCommand = jest.fn().mockReturnValue(true);
    Object.assign(document, { execCommand });

    setup();
    await userEvent.click(screen.getByRole('button', { name: /copy to clipboard/i }));

    await waitFor(() => expect(execCommand).toHaveBeenCalledWith('copy'));
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /copied/i })).toBeInTheDocument()
    );
    // The temporary textarea must not be left in the DOM.
    expect(document.querySelectorAll('textarea')).toHaveLength(1);
  });
});

describe('ExportPatchModal — download', () => {
  it('builds a Blob download under the given filename and revokes the URL', async () => {
    const createObjectURL = jest.fn().mockReturnValue('blob:fake');
    const revokeObjectURL = jest.fn();
    Object.assign(URL, { createObjectURL, revokeObjectURL });

    const clicked: HTMLAnchorElement[] = [];
    const realCreate = document.createElement.bind(document);
    jest.spyOn(document, 'createElement').mockImplementation((tag: string) => {
      const el = realCreate(tag);
      if (tag === 'a') {
        jest.spyOn(el as HTMLAnchorElement, 'click').mockImplementation(() => {
          clicked.push(el as HTMLAnchorElement);
        });
      }
      return el;
    });

    setup();
    await userEvent.click(screen.getByRole('button', { name: /download/i }));

    expect(createObjectURL).toHaveBeenCalledTimes(1);
    expect(createObjectURL.mock.calls[0][0]).toBeInstanceOf(Blob);
    expect(clicked).toHaveLength(1);
    expect(clicked[0].download).toBe('changes.patch');
    expect(clicked[0].href).toContain('blob:fake');
    // Not revoking leaks the object URL for the life of the document.
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:fake');
    // The temporary anchor must not be left behind.
    expect(document.querySelectorAll('a[download]')).toHaveLength(0);

    (document.createElement as jest.Mock).mockRestore();
  });
});
