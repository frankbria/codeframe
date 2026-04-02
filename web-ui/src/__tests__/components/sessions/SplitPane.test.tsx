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

type MatchMediaHandler = (e: { matches: boolean }) => void;

function mockMatchMedia(matches: boolean): { trigger: (m: boolean) => void } {
  const handlers: MatchMediaHandler[] = [];
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: jest.fn().mockImplementation((query: string) => ({
      matches,
      media: query,
      onchange: null,
      addListener: jest.fn(),
      removeListener: jest.fn(),
      addEventListener: (_: string, cb: MatchMediaHandler) => handlers.push(cb),
      removeEventListener: jest.fn(),
      dispatchEvent: jest.fn(),
    })),
  });
  return {
    trigger: (newMatches: boolean) => handlers.forEach((h) => h({ matches: newMatches })),
  };
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

// ── Helpers ──────────────────────────────────────────────────────────────

/** Render SplitPane and wait for isMobile useEffect to resolve. */
function renderSplitPane(props: Partial<Parameters<typeof SplitPane>[0]> = {}) {
  const result = render(
    <SplitPane
      left={<div>Left content</div>}
      right={<div>Right content</div>}
      {...props}
    />,
  );
  // Flush useEffect so isMobile resolves from null → false/true
  act(() => {});
  return result;
}

// ── Setup ────────────────────────────────────────────────────────────────

beforeEach(() => {
  localStorageMock.clear();
  mockMatchMedia(true); // desktop by default (matches = true means ≥768px)
});

afterEach(() => {
  jest.restoreAllMocks();
});

// ── Tests ────────────────────────────────────────────────────────────────

describe('SplitPane', () => {
  describe('rendering', () => {
    it('renders left and right children', () => {
      renderSplitPane();
      expect(screen.getByText('Left content')).toBeInTheDocument();
      expect(screen.getByText('Right content')).toBeInTheDocument();
    });

    it('uses defaultSplit=45 when no localStorage value exists', () => {
      renderSplitPane({ defaultSplit: 45 });
      expect(screen.getByTestId('split-pane-left')).toHaveStyle({ width: '45%' });
    });

    it('applies custom className to outer container', () => {
      renderSplitPane({ className: 'my-custom-class' });
      expect(screen.getByTestId('split-pane-container').className).toContain('my-custom-class');
    });
  });

  describe('localStorage', () => {
    it('restores split position from localStorage on mount', () => {
      localStorageMock.setItem('split-pane-position', '60');
      renderSplitPane();
      expect(screen.getByTestId('split-pane-left')).toHaveStyle({ width: '60%' });
    });

    it('uses custom storageKey', () => {
      localStorageMock.setItem('my-custom-key', '70');
      renderSplitPane({ storageKey: 'my-custom-key' });
      expect(screen.getByTestId('split-pane-left')).toHaveStyle({ width: '70%' });
    });

    it('ignores collapsed sentinels (0/100) and falls back to defaultSplit', () => {
      localStorageMock.setItem('split-pane-position', '0');
      renderSplitPane({ defaultSplit: 45 });
      expect(screen.getByTestId('split-pane-left')).toHaveStyle({ width: '45%' });
    });

    it('clamps stored value below min up to minPanePercent on reload', () => {
      localStorageMock.setItem('split-pane-position', '10');
      renderSplitPane({ minPanePercent: 15, defaultSplit: 45 });
      expect(screen.getByTestId('split-pane-left')).toHaveStyle({ width: '15%' });
    });

    it('clamps stored value above max down to 100-minPanePercent on reload', () => {
      localStorageMock.setItem('split-pane-position', '90');
      renderSplitPane({ minPanePercent: 15, defaultSplit: 45 });
      expect(screen.getByTestId('split-pane-left')).toHaveStyle({ width: '85%' });
    });

    it('clamps an out-of-range defaultSplit into the expanded range', () => {
      renderSplitPane({ defaultSplit: 5, minPanePercent: 15 });
      expect(screen.getByTestId('split-pane-left')).toHaveStyle({ width: '15%' });
    });

    it('persists position to localStorage on drag end', () => {
      mockContainerRect(0, 1000);
      renderSplitPane({ storageKey: 'test-key' });
      const divider = screen.getByTestId('split-pane-divider');

      fireEvent.mouseDown(divider);
      fireEvent.mouseMove(document, { clientX: 600 });
      fireEvent.mouseUp(document);

      expect(localStorageMock.getItem('test-key')).toBe('60');
    });

    it('does NOT write 0 to localStorage when left pane is collapsed', () => {
      localStorageMock.setItem('split-pane-position', '45');
      renderSplitPane({ storageKey: 'split-pane-position' });
      fireEvent.click(screen.getByTestId('collapse-left'));
      // Should still be 45, not 0
      expect(localStorageMock.getItem('split-pane-position')).toBe('45');
    });

    it('does NOT write 100 to localStorage when right pane is collapsed', () => {
      localStorageMock.setItem('split-pane-position', '45');
      renderSplitPane({ storageKey: 'split-pane-position' });
      fireEvent.click(screen.getByTestId('collapse-right'));
      expect(localStorageMock.getItem('split-pane-position')).toBe('45');
    });

    it('renders at defaultSplit after reload when previously collapsed', () => {
      // Simulate: user collapsed left pane, then reloaded page
      // localStorage should still have the valid position (45), not 0
      localStorageMock.setItem('split-pane-position', '45');
      renderSplitPane({ defaultSplit: 45 });
      // On reload the pane should open expanded at 45%
      expect(screen.getByTestId('split-pane-left')).toHaveStyle({ width: '45%' });
    });
  });

  describe('drag', () => {
    it('enforces minPanePercent on the left side during drag', () => {
      mockContainerRect(0, 1000);
      renderSplitPane({ storageKey: 'test-key' });
      const divider = screen.getByTestId('split-pane-divider');

      fireEvent.mouseDown(divider);
      fireEvent.mouseMove(document, { clientX: 50 }); // 5% — below min
      fireEvent.mouseUp(document);

      expect(localStorageMock.getItem('test-key')).toBe('15');
    });

    it('enforces minPanePercent on the right side during drag', () => {
      mockContainerRect(0, 1000);
      renderSplitPane({ storageKey: 'test-key' });
      const divider = screen.getByTestId('split-pane-divider');

      fireEvent.mouseDown(divider);
      fireEvent.mouseMove(document, { clientX: 980 }); // 98% — right pane below min
      fireEvent.mouseUp(document);

      expect(localStorageMock.getItem('test-key')).toBe('85');
    });

    it('does not move divider without mousedown first', () => {
      localStorageMock.setItem('split-pane-position', '45');
      mockContainerRect(0, 1000);
      renderSplitPane({ storageKey: 'split-pane-position' });

      fireEvent.mouseMove(document, { clientX: 700 });
      fireEvent.mouseUp(document);

      expect(localStorageMock.getItem('split-pane-position')).toBe('45');
    });

    it('outward drag from left-collapsed edge is a no-op (no width change, no storage write)', () => {
      mockContainerRect(0, 1000);
      renderSplitPane({ defaultSplit: 45, storageKey: 'test-key' });
      fireEvent.click(screen.getByTestId('collapse-left')); // splitPct → 0
      localStorageMock.clear();

      const divider = screen.getByTestId('split-pane-divider');
      fireEvent.mouseDown(divider); // livePercent.current resets to 0
      // clientX = -50 → rawPct = -5% (further left/outward)
      fireEvent.mouseMove(document, { clientX: -50 });
      fireEvent.mouseUp(document);

      expect(localStorageMock.getItem('test-key')).toBeNull();
      expect(screen.getByTestId('split-pane-left')).toHaveStyle({ width: '0%' });
    });

    it('outward drag from right-collapsed edge is a no-op (no width change, no storage write)', () => {
      mockContainerRect(0, 1000);
      renderSplitPane({ defaultSplit: 45, storageKey: 'test-key' });
      fireEvent.click(screen.getByTestId('collapse-right')); // splitPct → 100
      localStorageMock.clear();

      const divider = screen.getByTestId('split-pane-divider');
      fireEvent.mouseDown(divider); // livePercent.current resets to 100
      // clientX = 1050 → rawPct = 105% (further right/outward)
      fireEvent.mouseMove(document, { clientX: 1050 });
      fireEvent.mouseUp(document);

      expect(localStorageMock.getItem('test-key')).toBeNull();
      expect(screen.getByTestId('split-pane-right')).toHaveStyle({ width: '0%' });
    });

    it('inward drag from left-collapsed edge exits collapsed state and commits', () => {
      mockContainerRect(0, 1000);
      renderSplitPane({ defaultSplit: 45, minPanePercent: 15, storageKey: 'test-key' });
      fireEvent.click(screen.getByTestId('collapse-left')); // splitPct → 0

      const divider = screen.getByTestId('split-pane-divider');
      fireEvent.mouseDown(divider); // livePercent.current resets to 0
      // clientX = 300 → rawPct = 30% (inward)
      fireEvent.mouseMove(document, { clientX: 300 });
      fireEvent.mouseUp(document);

      expect(localStorageMock.getItem('test-key')).toBe('30');
      expect(screen.getByTestId('split-pane-left')).toHaveStyle({ width: '30%' });
    });

    it('inward drag from right-collapsed edge exits collapsed state and commits', () => {
      mockContainerRect(0, 1000);
      renderSplitPane({ defaultSplit: 45, minPanePercent: 15, storageKey: 'test-key' });
      fireEvent.click(screen.getByTestId('collapse-right')); // splitPct → 100

      const divider = screen.getByTestId('split-pane-divider');
      fireEvent.mouseDown(divider); // livePercent.current resets to 100
      // clientX = 700 → rawPct = 70% (inward, right pane gets 30%)
      fireEvent.mouseMove(document, { clientX: 700 });
      fireEvent.mouseUp(document);

      expect(localStorageMock.getItem('test-key')).toBe('70');
      expect(screen.getByTestId('split-pane-left')).toHaveStyle({ width: '70%' });
    });

    it('plain click on divider does not reopen a collapsed pane', () => {
      // mousedown + immediate mouseup (no mousemove) must not commit livePercent
      renderSplitPane({ defaultSplit: 45, storageKey: 'test-key' });
      fireEvent.click(screen.getByTestId('collapse-left')); // collapse → splitPct=0
      localStorageMock.clear();

      const divider = screen.getByTestId('split-pane-divider');
      fireEvent.mouseDown(divider);
      fireEvent.mouseUp(document); // no mousemove in between

      // Storage should remain untouched — pane stays collapsed
      expect(localStorageMock.getItem('test-key')).toBeNull();
      expect(screen.getByTestId('split-pane-left')).toHaveStyle({ width: '0%' });
    });
  });

  describe('keyboard resize', () => {
    it('moves divider left with ArrowLeft key', () => {
      renderSplitPane({ defaultSplit: 50, storageKey: 'test-key' });
      const divider = screen.getByTestId('split-pane-divider');
      fireEvent.keyDown(divider, { key: 'ArrowLeft' });
      expect(localStorageMock.getItem('test-key')).toBe('45');
    });

    it('moves divider right with ArrowRight key', () => {
      renderSplitPane({ defaultSplit: 50, storageKey: 'test-key' });
      const divider = screen.getByTestId('split-pane-divider');
      fireEvent.keyDown(divider, { key: 'ArrowRight' });
      expect(localStorageMock.getItem('test-key')).toBe('55');
    });

    it('clamps keyboard resize to minPanePercent', () => {
      renderSplitPane({ defaultSplit: 16, minPanePercent: 15, storageKey: 'test-key' });
      const divider = screen.getByTestId('split-pane-divider');
      fireEvent.keyDown(divider, { key: 'ArrowLeft' });
      fireEvent.keyDown(divider, { key: 'ArrowLeft' });
      expect(localStorageMock.getItem('test-key')).toBe('15');
    });

    it('ArrowLeft is a no-op when left pane is fully collapsed (splitPct=0)', () => {
      renderSplitPane({ defaultSplit: 45, storageKey: 'test-key' });
      const divider = screen.getByTestId('split-pane-divider');
      fireEvent.click(screen.getByTestId('collapse-left')); // splitPct → 0
      localStorageMock.clear(); // clear so we can detect any write
      fireEvent.keyDown(divider, { key: 'ArrowLeft' });
      expect(localStorageMock.getItem('test-key')).toBeNull();
    });

    it('ArrowRight restores left-collapsed pane to minPanePercent', () => {
      renderSplitPane({ defaultSplit: 45, minPanePercent: 15, storageKey: 'test-key' });
      const divider = screen.getByTestId('split-pane-divider');
      fireEvent.click(screen.getByTestId('collapse-left')); // splitPct → 0
      fireEvent.keyDown(divider, { key: 'ArrowRight' });
      expect(localStorageMock.getItem('test-key')).toBe('15');
    });

    it('ArrowRight is a no-op when right pane is fully collapsed (splitPct=100)', () => {
      renderSplitPane({ defaultSplit: 45, storageKey: 'test-key' });
      const divider = screen.getByTestId('split-pane-divider');
      fireEvent.click(screen.getByTestId('collapse-right')); // splitPct → 100
      localStorageMock.clear();
      fireEvent.keyDown(divider, { key: 'ArrowRight' });
      expect(localStorageMock.getItem('test-key')).toBeNull();
    });

    it('ArrowLeft restores right-collapsed pane to 100-minPanePercent', () => {
      renderSplitPane({ defaultSplit: 45, minPanePercent: 15, storageKey: 'test-key' });
      const divider = screen.getByTestId('split-pane-divider');
      fireEvent.click(screen.getByTestId('collapse-right')); // splitPct → 100
      fireEvent.keyDown(divider, { key: 'ArrowLeft' });
      expect(localStorageMock.getItem('test-key')).toBe('85');
    });
  });

  describe('collapse/expand', () => {
    it('collapses left pane', () => {
      renderSplitPane();
      fireEvent.click(screen.getByTestId('collapse-left'));
      expect(screen.getByTestId('split-pane-left')).toHaveStyle({ width: '0%' });
    });

    it('expands left pane to original position', () => {
      renderSplitPane({ defaultSplit: 45 });
      const btn = screen.getByTestId('collapse-left');
      fireEvent.click(btn); // collapse
      fireEvent.click(btn); // expand
      expect(screen.getByTestId('split-pane-left')).toHaveStyle({ width: '45%' });
    });

    it('collapses right pane', () => {
      renderSplitPane();
      fireEvent.click(screen.getByTestId('collapse-right'));
      expect(screen.getByTestId('split-pane-right')).toHaveStyle({ width: '0%' });
    });

    it('expands right pane to original position', () => {
      renderSplitPane({ defaultSplit: 45 });
      const btn = screen.getByTestId('collapse-right');
      fireEvent.click(btn); // collapse
      fireEvent.click(btn); // expand
      expect(screen.getByTestId('split-pane-right')).toHaveStyle({ width: '55%' });
    });

    it('restores correct position after collapse-right → collapse-left → expand-left', () => {
      // Regression: lastNonCollapsed must not be corrupted by cross-pane collapse
      renderSplitPane({ defaultSplit: 45 });
      fireEvent.click(screen.getByTestId('collapse-right')); // splitPct → 100
      fireEvent.click(screen.getByTestId('collapse-left'));  // collapse left while right was collapsed
      fireEvent.click(screen.getByTestId('collapse-left'));  // expand left
      // Should restore to 45, not 100
      expect(screen.getByTestId('split-pane-left')).toHaveStyle({ width: '45%' });
    });
  });

  describe('accessibility', () => {
    it('divider has role="separator" and aria-orientation="vertical"', () => {
      renderSplitPane();
      const divider = screen.getByTestId('split-pane-divider');
      expect(divider).toHaveAttribute('role', 'separator');
      expect(divider).toHaveAttribute('aria-orientation', 'vertical');
    });

    it('divider exposes aria-valuenow', () => {
      renderSplitPane({ defaultSplit: 45 });
      expect(screen.getByTestId('split-pane-divider')).toHaveAttribute('aria-valuenow', '45');
    });

    it('collapse buttons have type="button"', () => {
      renderSplitPane();
      expect(screen.getByTestId('collapse-left')).toHaveAttribute('type', 'button');
      expect(screen.getByTestId('collapse-right')).toHaveAttribute('type', 'button');
    });

    it('collapse buttons have descriptive aria-labels', () => {
      renderSplitPane();
      expect(screen.getByTestId('collapse-left')).toHaveAttribute('aria-label', 'Collapse left pane');
      expect(screen.getByTestId('collapse-right')).toHaveAttribute('aria-label', 'Collapse right pane');
    });

    it('aria-label flips when pane is collapsed', () => {
      renderSplitPane();
      fireEvent.click(screen.getByTestId('collapse-left'));
      expect(screen.getByTestId('collapse-left')).toHaveAttribute('aria-label', 'Expand left pane');
    });
  });

  describe('mobile layout', () => {
    it('stacks vertically on mobile', () => {
      mockMatchMedia(false); // matches=false means <768px
      renderSplitPane();
      expect(screen.getByTestId('split-pane-container').className).toContain('flex-col');
    });

    it('hides divider track on mobile', () => {
      mockMatchMedia(false);
      renderSplitPane();
      expect(screen.getByTestId('split-pane-divider-track').className).toContain('hidden');
    });

    it('switches to desktop layout when viewport widens', () => {
      const mq = mockMatchMedia(false); // start mobile
      renderSplitPane();
      act(() => mq.trigger(true)); // simulate viewport ≥768px
      expect(screen.getByTestId('split-pane-container').className).toContain('flex-row');
    });
  });
});
