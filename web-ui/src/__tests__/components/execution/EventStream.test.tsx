/**
 * EventStream behavioural coverage (issue #964).
 *
 * 276 LOC with no unit tests. It owns three things a user notices immediately
 * when they break: event ordering, auto-scroll (and the "New events" escape
 * hatch when you have scrolled up), and the smart/raw view toggle that groups
 * consecutive file reads and edits.
 */
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { EventStream } from '@/components/execution/EventStream';

// Render each event as a plain line so ordering is assertable as text.
jest.mock('@/components/execution/EventItem', () => ({
  EventItem: ({ event }: { event: Record<string, unknown> }) => (
    <div data-testid="event-item">
      {(event.message as string) ?? (event.line as string) ?? String(event.event_type)}
    </div>
  ),
}));

let scrollIntoView: jest.Mock;

beforeEach(() => {
  scrollIntoView = jest.fn();
  window.HTMLElement.prototype.scrollIntoView = scrollIntoView;
});

function progress(message: string, timestamp: string) {
  return { event_type: 'progress', message, timestamp } as never;
}

function heartbeat(timestamp: string) {
  return { event_type: 'heartbeat', timestamp } as never;
}

function renderStream(events: unknown[]) {
  return render(
    <EventStream events={events as never[]} workspacePath="/ws" />
  );
}

describe('EventStream — ordering and content', () => {
  it('renders events in the order received', () => {
    renderStream([
      progress('first thing', '2026-01-01T00:00:00Z'),
      progress('second thing', '2026-01-01T00:00:01Z'),
      progress('third thing', '2026-01-01T00:00:02Z'),
    ]);

    const lines = screen.getAllByTestId('event-item').map((n) => n.textContent);
    expect(lines).toEqual(['first thing', 'second thing', 'third thing']);
  });

  it('hides heartbeats, which are transport noise', () => {
    renderStream([
      progress('real event', '2026-01-01T00:00:00Z'),
      heartbeat('2026-01-01T00:00:01Z'),
      heartbeat('2026-01-01T00:00:02Z'),
    ]);

    const lines = screen.getAllByTestId('event-item').map((n) => n.textContent);
    expect(lines).toEqual(['real event']);
  });

  it('shows a waiting state when there is nothing but heartbeats', () => {
    renderStream([heartbeat('2026-01-01T00:00:00Z')]);
    expect(screen.getByText(/waiting for events/i)).toBeInTheDocument();
  });

  it('exposes the stream as a live log region for screen readers', () => {
    renderStream([progress('x', '2026-01-01T00:00:00Z')]);
    const log = screen.getByRole('log');
    expect(log).toHaveAttribute('aria-live', 'polite');
    expect(log).toHaveAccessibleName(/execution event stream/i);
  });
});

describe('EventStream — smart grouping', () => {
  it('collapses consecutive reads into one row', () => {
    renderStream([
      progress('Reading file: a.ts', '2026-01-01T00:00:00Z'),
      progress('Reading file: b.ts', '2026-01-01T00:00:01Z'),
      progress('Reading file: c.ts', '2026-01-01T00:00:02Z'),
    ]);

    // Grouped, so the individual EventItems are not rendered.
    expect(screen.queryAllByTestId('event-item')).toHaveLength(0);
  });

  it('collapses consecutive edits but leaves a lone edit alone', () => {
    renderStream([
      progress('Editing file: a.ts', '2026-01-01T00:00:00Z'),
      progress('Editing file: b.ts', '2026-01-01T00:00:01Z'),
    ]);
    expect(screen.queryAllByTestId('event-item')).toHaveLength(0);
  });

  it('renders a single edit as an ordinary event', () => {
    renderStream([
      progress('Editing file: only.ts', '2026-01-01T00:00:00Z'),
      progress('something else', '2026-01-01T00:00:01Z'),
    ]);
    const lines = screen.getAllByTestId('event-item').map((n) => n.textContent);
    expect(lines).toEqual(['Editing file: only.ts', 'something else']);
  });

  it('shows every event unmodified in raw view', async () => {
    renderStream([
      progress('Reading file: a.ts', '2026-01-01T00:00:00Z'),
      progress('Reading file: b.ts', '2026-01-01T00:00:01Z'),
    ]);
    expect(screen.queryAllByTestId('event-item')).toHaveLength(0);

    await userEvent.click(screen.getByRole('button', { name: /show all events/i }));

    const lines = screen.getAllByTestId('event-item').map((n) => n.textContent);
    expect(lines).toEqual(['Reading file: a.ts', 'Reading file: b.ts']);
    expect(screen.getByRole('button', { name: /smart view/i })).toBeInTheDocument();
  });
});

describe('EventStream — autoscroll', () => {
  it('scrolls to the newest event by default', async () => {
    const { rerender } = renderStream([progress('one', '2026-01-01T00:00:00Z')]);
    scrollIntoView.mockClear();

    rerender(
      <EventStream
        events={
          [
            progress('one', '2026-01-01T00:00:00Z'),
            progress('two', '2026-01-01T00:00:01Z'),
          ] as never[]
        }
        workspacePath="/ws"
      />
    );

    await waitFor(() => expect(scrollIntoView).toHaveBeenCalled());
  });

  it('stops following and offers "New events" once the user scrolls up', async () => {
    const { rerender } = renderStream([progress('one', '2026-01-01T00:00:00Z')]);
    const log = screen.getByRole('log');

    // Simulate being scrolled well away from the bottom.
    Object.defineProperty(log, 'scrollTop', { value: 0, configurable: true });
    Object.defineProperty(log, 'scrollHeight', { value: 1000, configurable: true });
    Object.defineProperty(log, 'clientHeight', { value: 200, configurable: true });
    fireEvent.scroll(log);

    scrollIntoView.mockClear();
    rerender(
      <EventStream
        events={
          [
            progress('one', '2026-01-01T00:00:00Z'),
            progress('two', '2026-01-01T00:00:01Z'),
          ] as never[]
        }
        workspacePath="/ws"
      />
    );

    await waitFor(() =>
      expect(screen.getByRole('button', { name: /new events/i })).toBeInTheDocument()
    );
    expect(scrollIntoView).not.toHaveBeenCalled();
  });

  it('resumes following when the user scrolls back to the bottom', async () => {
    renderStream([progress('one', '2026-01-01T00:00:00Z')]);
    const log = screen.getByRole('log');

    Object.defineProperty(log, 'scrollTop', { value: 0, configurable: true });
    Object.defineProperty(log, 'scrollHeight', { value: 1000, configurable: true });
    Object.defineProperty(log, 'clientHeight', { value: 200, configurable: true });
    fireEvent.scroll(log);

    // Back to the bottom (within the 40px threshold).
    Object.defineProperty(log, 'scrollTop', { value: 800, configurable: true });
    fireEvent.scroll(log);

    await waitFor(() =>
      expect(screen.queryByRole('button', { name: /new events/i })).not.toBeInTheDocument()
    );
  });

  it('"New events" jumps to the bottom and dismisses itself', async () => {
    const { rerender } = renderStream([progress('one', '2026-01-01T00:00:00Z')]);
    const log = screen.getByRole('log');

    Object.defineProperty(log, 'scrollTop', { value: 0, configurable: true });
    Object.defineProperty(log, 'scrollHeight', { value: 1000, configurable: true });
    Object.defineProperty(log, 'clientHeight', { value: 200, configurable: true });
    fireEvent.scroll(log);

    rerender(
      <EventStream
        events={
          [
            progress('one', '2026-01-01T00:00:00Z'),
            progress('two', '2026-01-01T00:00:01Z'),
          ] as never[]
        }
        workspacePath="/ws"
      />
    );

    const button = await screen.findByRole('button', { name: /new events/i });
    scrollIntoView.mockClear();
    await userEvent.click(button);

    expect(scrollIntoView).toHaveBeenCalled();
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: /new events/i })).not.toBeInTheDocument()
    );
  });
});
