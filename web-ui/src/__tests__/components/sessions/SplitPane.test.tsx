import { render, screen, fireEvent, act } from '@testing-library/react';
import { SplitPane } from '@/components/sessions/SplitPane';

// ── localStorage mock ────────────────────────────────────────────────────

const localStorageMock = (() => {
  let store: Record<string, string> = {};
  return {
    getItem: (key: string) => store[key] ?? null,
    setItem: (key: string, value: string) => {
      store[key] = value;
    },
    removeItem: (key: string) => {
      delete store[key];
    },
    clear: () => {
      store = {};
    },
  };
})();

Object.defineProperty(window, 'localStorage', { value: localStorageMock });

// ── matchMedia mock ──────────────────────────────────────────────────────

function mockMatchMedia(matches: boolean) {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: jest.fn().mockImplementation((query: string) => ({
      matches,
      media: query,
      onchange: null,
      addListener: jest.fn(),
      removeListener: jest.fn(),
      addEventListener: jest.fn(),
      removeEventListener: jest.fn(),
      dispatchEvent: jest.fn(),
    })),
  });
}

// ── getBoundingClientRect mock ───────────────────────────────────────────

function mockContainerRect(left = 0, width = 1000) {
  jest.spyOn(Element.prototype, 'getBoundingClientRect').mockReturnValue({
    left,
    width,
    top: 0,
    right: left + width,
    bottom: 100,
    height: 100,
    x: left,
    y: 0,
    toJSON: () => ({}),
  });
}

// ── Tests ────────────────────────────────────────────────────────────────

beforeEach(() => {
  localStorageMock.clear();
  mockMatchMedia(true); // desktop by default
});

afterEach(() => {
  jest.restoreAllMocks();
});

describe('SplitPane', () => {
  it('renders left and right children', () => {
    render(<SplitPane left={<div>Left content</div>} right={<div>Right content</div>} />);
    expect(screen.getByText('Left content')).toBeInTheDocument();
    expect(screen.getByText('Right content')).toBeInTheDocument();
  });

  it('uses defaultSplit=45 when no localStorage value exists', () => {
    render(<SplitPane left={<div>L</div>} right={<div>R</div>} defaultSplit={45} />);
    const leftPane = screen.getByTestId('split-pane-left');
    expect(leftPane).toHaveStyle({ width: '45%' });
  });

  it('restores split position from localStorage on mount', () => {
    localStorageMock.setItem('split-pane-position', '60');
    render(<SplitPane left={<div>L</div>} right={<div>R</div>} />);
    const leftPane = screen.getByTestId('split-pane-left');
    expect(leftPane).toHaveStyle({ width: '60%' });
  });

  it('uses custom storageKey for localStorage', () => {
    localStorageMock.setItem('my-custom-key', '70');
    render(<SplitPane left={<div>L</div>} right={<div>R</div>} storageKey="my-custom-key" />);
    const leftPane = screen.getByTestId('split-pane-left');
    expect(leftPane).toHaveStyle({ width: '70%' });
  });

  it('persists position to localStorage on drag end', () => {
    mockContainerRect(0, 1000);
    render(<SplitPane left={<div>L</div>} right={<div>R</div>} storageKey="test-key" />);
    const divider = screen.getByTestId('split-pane-divider');

    fireEvent.mouseDown(divider);
    fireEvent.mouseMove(document, { clientX: 600 });
    fireEvent.mouseUp(document);

    expect(localStorageMock.getItem('test-key')).toBe('60');
  });

  it('enforces minPanePercent during drag (default 15%)', () => {
    mockContainerRect(0, 1000);
    render(<SplitPane left={<div>L</div>} right={<div>R</div>} storageKey="test-key" />);
    const divider = screen.getByTestId('split-pane-divider');

    fireEvent.mouseDown(divider);
    fireEvent.mouseMove(document, { clientX: 50 }); // 5% — below min
    fireEvent.mouseUp(document);

    // Should be clamped to 15%
    expect(localStorageMock.getItem('test-key')).toBe('15');
  });

  it('enforces minPanePercent on the right side during drag', () => {
    mockContainerRect(0, 1000);
    render(<SplitPane left={<div>L</div>} right={<div>R</div>} storageKey="test-key" />);
    const divider = screen.getByTestId('split-pane-divider');

    fireEvent.mouseDown(divider);
    fireEvent.mouseMove(document, { clientX: 980 }); // 98% — right pane below min
    fireEvent.mouseUp(document);

    // Should be clamped to 85% (100 - 15)
    expect(localStorageMock.getItem('test-key')).toBe('85');
  });

  it('collapses left pane when left collapse button is clicked', () => {
    render(<SplitPane left={<div>L</div>} right={<div>R</div>} />);
    const collapseLeft = screen.getByTestId('collapse-left');
    fireEvent.click(collapseLeft);
    const leftPane = screen.getByTestId('split-pane-left');
    expect(leftPane).toHaveStyle({ width: '0%' });
  });

  it('expands left pane when collapse button is clicked again', () => {
    render(<SplitPane left={<div>L</div>} right={<div>R</div>} defaultSplit={45} />);
    const collapseLeft = screen.getByTestId('collapse-left');
    fireEvent.click(collapseLeft); // collapse
    fireEvent.click(collapseLeft); // expand
    const leftPane = screen.getByTestId('split-pane-left');
    expect(leftPane).toHaveStyle({ width: '45%' });
  });

  it('collapses right pane when right collapse button is clicked', () => {
    render(<SplitPane left={<div>L</div>} right={<div>R</div>} />);
    const collapseRight = screen.getByTestId('collapse-right');
    fireEvent.click(collapseRight);
    const rightPane = screen.getByTestId('split-pane-right');
    expect(rightPane).toHaveStyle({ width: '0%' });
  });

  it('expands right pane when collapse button is clicked again', () => {
    render(<SplitPane left={<div>L</div>} right={<div>R</div>} defaultSplit={45} />);
    const collapseRight = screen.getByTestId('collapse-right');
    fireEvent.click(collapseRight); // collapse
    fireEvent.click(collapseRight); // expand
    const rightPane = screen.getByTestId('split-pane-right');
    expect(rightPane).toHaveStyle({ width: '55%' });
  });

  it('does not apply inline width styles on mobile', () => {
    mockMatchMedia(false); // mobile
    render(<SplitPane left={<div>L</div>} right={<div>R</div>} />);
    const container = screen.getByTestId('split-pane-container');
    expect(container.className).toContain('flex-col');
  });

  it('hides divider on mobile', () => {
    mockMatchMedia(false);
    render(<SplitPane left={<div>L</div>} right={<div>R</div>} />);
    const divider = screen.getByTestId('split-pane-divider');
    expect(divider.className).toContain('hidden');
  });

  it('applies custom className to outer container', () => {
    render(
      <SplitPane left={<div>L</div>} right={<div>R</div>} className="my-custom-class" />,
    );
    const container = screen.getByTestId('split-pane-container');
    expect(container.className).toContain('my-custom-class');
  });

  it('does not move divider if mouse was not pressed (no drag started)', () => {
    localStorageMock.setItem('split-pane-position', '45');
    mockContainerRect(0, 1000);
    render(<SplitPane left={<div>L</div>} right={<div>R</div>} storageKey="split-pane-position" />);

    // Move without mousedown
    fireEvent.mouseMove(document, { clientX: 700 });
    fireEvent.mouseUp(document);

    expect(localStorageMock.getItem('split-pane-position')).toBe('45');
  });
});
