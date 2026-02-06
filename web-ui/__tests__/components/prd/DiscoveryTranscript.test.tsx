import { render, screen } from '@testing-library/react';
import { DiscoveryTranscript } from '@/components/prd/DiscoveryTranscript';
import type { DiscoveryMessage } from '@/types';

// Mock scrollIntoView
window.HTMLElement.prototype.scrollIntoView = jest.fn();

describe('DiscoveryTranscript', () => {
  it('renders assistant messages with AI avatar', () => {
    const messages: DiscoveryMessage[] = [
      { role: 'assistant', content: 'What is your project about?', timestamp: '2026-01-15T10:00:00Z' },
    ];
    render(<DiscoveryTranscript messages={messages} isThinking={false} />);

    expect(screen.getByText('What is your project about?')).toBeInTheDocument();
    expect(screen.getByTestId('icon-ArtificialIntelligence01Icon')).toBeInTheDocument();
  });

  it('renders user messages without avatar', () => {
    const messages: DiscoveryMessage[] = [
      { role: 'user', content: 'A task management tool', timestamp: '2026-01-15T10:01:00Z' },
    ];
    render(<DiscoveryTranscript messages={messages} isThinking={false} />);

    expect(screen.getByText('A task management tool')).toBeInTheDocument();
    // User messages have no AI icon
    expect(screen.queryByTestId('icon-ArtificialIntelligence01Icon')).not.toBeInTheDocument();
  });

  it('renders a conversation with multiple messages', () => {
    const messages: DiscoveryMessage[] = [
      { role: 'assistant', content: 'Question 1?', timestamp: '2026-01-15T10:00:00Z' },
      { role: 'user', content: 'Answer 1', timestamp: '2026-01-15T10:01:00Z' },
      { role: 'assistant', content: 'Question 2?', timestamp: '2026-01-15T10:02:00Z' },
    ];
    render(<DiscoveryTranscript messages={messages} isThinking={false} />);

    expect(screen.getByText('Question 1?')).toBeInTheDocument();
    expect(screen.getByText('Answer 1')).toBeInTheDocument();
    expect(screen.getByText('Question 2?')).toBeInTheDocument();
  });

  it('shows thinking indicator when isThinking is true', () => {
    render(<DiscoveryTranscript messages={[]} isThinking={true} />);

    // The thinking indicator has bounce-dot spans
    const dots = document.querySelectorAll('.animate-bounce');
    expect(dots).toHaveLength(3);
  });

  it('hides thinking indicator when isThinking is false', () => {
    render(<DiscoveryTranscript messages={[]} isThinking={false} />);

    const dots = document.querySelectorAll('.animate-bounce');
    expect(dots).toHaveLength(0);
  });

  it('renders empty state with no messages', () => {
    const { container } = render(
      <DiscoveryTranscript messages={[]} isThinking={false} />
    );
    // Should render the container div but no message bubbles
    expect(container.querySelector('.space-y-4')).toBeInTheDocument();
  });
});
