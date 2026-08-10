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
// The raw bytes the endpoint returns, written out literally: jsdom has no
// TextEncoder, and a literal array shows the point anyway — byte 0xe9 is not
// valid UTF-8, and the download must carry it through unchanged (#1077).
const PATCH_BYTES = new Uint8Array([
  0x2b, 0x63, 0x61, 0x66, // "+caf"
  0xe9, // the non-UTF-8 byte
  0x0a, // "\n"
]).buffer;

function setup(overrides: Record<string, unknown> = {}) {
  const onClose = jest.fn();
  render(
    <ExportPatchModal
      open
      onClose={onClose}
      patchContent={PATCH}
      patchBytes={PATCH_BYTES}
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
  it('downloads the raw bytes, not the re-encoded display string (#1077)', async () => {
    const createObjectURL = jest.fn().mockReturnValue('blob:fake');
    Object.assign(URL, { createObjectURL, revokeObjectURL: jest.fn() });

    const realCreate = document.createElement.bind(document);
    jest.spyOn(document, 'createElement').mockImplementation((tag: string) => {
      const el = realCreate(tag);
      if (tag === 'a') {
        jest.spyOn(el as HTMLAnchorElement, 'click').mockImplementation(() => {});
      }
      return el;
    });

    // jsdom's Blob has no arrayBuffer(), so capture what the constructor was
    // handed — which is the claim under test: bytes, not the display string.
    const RealBlob = global.Blob;
    const parts: unknown[][] = [];
    // @ts-expect-error - replacing the constructor for the assertion below
    global.Blob = function (p: unknown[], opts?: BlobPropertyBag) {
      parts.push(p);
      return new RealBlob(p as BlobPart[], opts);
    };

    setup();
    await userEvent.click(screen.getByRole('button', { name: /download/i }));

    global.Blob = RealBlob;

    const bytes = new Uint8Array(parts[0][0] as ArrayBuffer);
    // 0xe9 survives. Building the Blob from `patchContent` would have
    // re-encoded it as UTF-8 (0xc3 0xa9) and broken `git apply`.
    expect(Array.from(bytes)).toEqual([0x2b, 0x63, 0x61, 0x66, 0xe9, 0x0a]);

    (document.createElement as jest.Mock).mockRestore();
  });


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
