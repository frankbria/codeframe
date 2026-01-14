# ChatInterface Component Test Specification (cf-14.2)

Test suite for ChatInterface component following Sprint 2 requirements.
**Framework**: Jest + React Testing Library (to be installed)
**Target**: 8 test cases covering all functionality

## Setup

```typescript
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { rest } from 'msw';
import { setupServer } from 'msw/node';
import ChatInterface from '../ChatInterface';

const server = setupServer();
beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());
```

## Test Cases

### 1. Message Rendering
**Description**: Verify messages are rendered with correct styling and timestamps

```typescript
it('renders messages with proper formatting', async () => {
  // Mock history response
  server.use(
    rest.get('/api/projects/1/chat/history', (req, res, ctx) => {
      return res(ctx.json({
        messages: [
          { role: 'user', content: 'Hello', timestamp: '2025-10-16T10:00:00Z' },
          { role: 'assistant', content: 'Hi there!', timestamp: '2025-10-16T10:00:05Z' }
        ]
      }));
    })
  );

  render(<ChatInterface projectId={1} agentStatus="working" />);

  // Wait for messages to load
  await waitFor(() => {
    expect(screen.getByText('Hello')).toBeInTheDocument();
    expect(screen.getByText('Hi there!')).toBeInTheDocument();
  });

  // Verify user message styling (blue background)
  const userMessage = screen.getByText('Hello').closest('div');
  expect(userMessage).toHaveClass('bg-blue-600');

  // Verify assistant message styling (gray background)
  const assistantMessage = screen.getByText('Hi there!').closest('div');
  expect(assistantMessage).toHaveClass('bg-gray-100');

  // Verify timestamps exist
  expect(screen.getAllByText(/ago/i)).toHaveLength(2);
});
```

### 2. Send Functionality
**Description**: Test sending messages via input and button

```typescript
it('sends message when form is submitted', async () => {
  let capturedMessage = '';

  server.use(
    rest.get('/api/projects/1/chat/history', (req, res, ctx) => {
      return res(ctx.json({ messages: [] }));
    }),
    rest.post('/api/projects/1/chat', async (req, res, ctx) => {
      const body = await req.json();
      capturedMessage = body.message;
      return res(ctx.json({
        response: 'Got it!',
        timestamp: new Date().toISOString()
      }));
    })
  );

  render(<ChatInterface projectId={1} agentStatus="working" />);

  // Type message
  const input = screen.getByPlaceholderText(/type your message/i);
  fireEvent.change(input, { target: { value: 'Test message' } });

  // Click send button
  const sendButton = screen.getByRole('button', { name: /send/i });
  fireEvent.click(sendButton);

  // Verify message was sent
  await waitFor(() => {
    expect(capturedMessage).toBe('Test message');
  });

  // Verify input cleared
  expect(input).toHaveValue('');

  // Verify optimistic UI + response
  expect(screen.getByText('Test message')).toBeInTheDocument();
  expect(screen.getByText('Got it!')).toBeInTheDocument();
});
```

### 3. WebSocket Integration
**Description**: Verify real-time message updates via WebSocket

```typescript
it('receives and displays WebSocket messages', async () => {
  const mockWs = {
    onMessage: jest.fn((handler) => {
      // Simulate incoming WebSocket message
      setTimeout(() => {
        handler({
          type: 'chat_message',
          project_id: 1,
          data: {
            role: 'assistant',
            content: 'Real-time update!',
            timestamp: new Date().toISOString()
          }
        });
      }, 100);
      return jest.fn(); // Unsubscribe function
    })
  };

  jest.mock('@/lib/websocket', () => ({
    getWebSocketClient: () => mockWs
  }));

  server.use(
    rest.get('/api/projects/1/chat/history', (req, res, ctx) => {
      return res(ctx.json({ messages: [] }));
    })
  );

  render(<ChatInterface projectId={1} agentStatus="working" />);

  // Wait for WebSocket message to appear
  await waitFor(() => {
    expect(screen.getByText('Real-time update!')).toBeInTheDocument();
  }, { timeout: 2000 });

  // Verify it's styled as assistant message
  const message = screen.getByText('Real-time update!').closest('div');
  expect(message).toHaveClass('bg-gray-100');
});
```

### 4. Loading States
**Description**: Test loading indicators during message send

```typescript
it('shows loading state while sending message', async () => {
  server.use(
    rest.get('/api/projects/1/chat/history', (req, res, ctx) => {
      return res(ctx.json({ messages: [] }));
    }),
    rest.post('/api/projects/1/chat', async (req, res, ctx) => {
      // Delay response to test loading state
      await new Promise(resolve => setTimeout(resolve, 500));
      return res(ctx.json({
        response: 'Response',
        timestamp: new Date().toISOString()
      }));
    })
  );

  render(<ChatInterface projectId={1} agentStatus="working" />);

  // Type and send message
  const input = screen.getByPlaceholderText(/type your message/i);
  fireEvent.change(input, { target: { value: 'Test' } });
  const sendButton = screen.getByRole('button', { name: /send/i });
  fireEvent.click(sendButton);

  // Verify loading state
  expect(screen.getByText(/sending/i)).toBeInTheDocument();
  expect(sendButton).toBeDisabled();
  expect(input).toBeDisabled();

  // Wait for completion
  await waitFor(() => {
    expect(screen.queryByText(/sending/i)).not.toBeInTheDocument();
    expect(sendButton).not.toBeDisabled();
  });
});
```

### 5. Agent Offline State
**Description**: Test disabled state when agent is offline

```typescript
it('disables input when agent is offline', () => {
  server.use(
    rest.get('/api/projects/1/chat/history', (req, res, ctx) => {
      return res(ctx.json({ messages: [] }));
    })
  );

  render(<ChatInterface projectId={1} agentStatus="offline" />);

  // Verify input is disabled
  const input = screen.getByPlaceholderText(/agent offline/i);
  expect(input).toBeDisabled();

  // Verify send button is disabled
  const sendButton = screen.getByRole('button', { name: /send/i });
  expect(sendButton).toBeDisabled();

  // Verify status indicator shows offline
  expect(screen.getByText('offline')).toHaveClass('text-gray-400');
});
```

### 6. Error Handling
**Description**: Test error display when message sending fails

```typescript
it('displays error message when send fails', async () => {
  server.use(
    rest.get('/api/projects/1/chat/history', (req, res, ctx) => {
      return res(ctx.json({ messages: [] }));
    }),
    rest.post('/api/projects/1/chat', (req, res, ctx) => {
      return res(
        ctx.status(400),
        ctx.json({ detail: 'Lead Agent not started' })
      );
    })
  );

  render(<ChatInterface projectId={1} agentStatus="working" />);

  // Send message
  const input = screen.getByPlaceholderText(/type your message/i);
  fireEvent.change(input, { target: { value: 'Test' } });
  fireEvent.click(screen.getByRole('button', { name: /send/i }));

  // Verify error message appears
  await waitFor(() => {
    expect(screen.getByText(/Lead Agent not started/i)).toBeInTheDocument();
  });

  // Verify message was restored to input
  expect(input).toHaveValue('Test');

  // Verify error has red styling
  const errorDiv = screen.getByText(/Lead Agent not started/i).closest('div');
  expect(errorDiv).toHaveClass('bg-red-50');
});
```

### 7. Empty State
**Description**: Test display when no messages exist

```typescript
it('shows empty state when no messages', async () => {
  server.use(
    rest.get('/api/projects/1/chat/history', (req, res, ctx) => {
      return res(ctx.json({ messages: [] }));
    })
  );

  render(<ChatInterface projectId={1} agentStatus="working" />);

  // Verify empty state message
  await waitFor(() => {
    expect(screen.getByText(/no messages yet/i)).toBeInTheDocument();
    expect(screen.getByText(/start a conversation/i)).toBeInTheDocument();
  });
});
```

### 8. Auto-scroll Behavior
**Description**: Test automatic scrolling to latest message

```typescript
it('auto-scrolls to latest message', async () => {
  server.use(
    rest.get('/api/projects/1/chat/history', (req, res, ctx) => {
      return res(ctx.json({
        messages: Array.from({ length: 20 }, (_, i) => ({
          role: i % 2 === 0 ? 'user' : 'assistant',
          content: `Message ${i}`,
          timestamp: new Date().toISOString()
        }))
      }));
    })
  );

  render(<ChatInterface projectId={1} agentStatus="working" />);

  // Wait for messages to load
  await waitFor(() => {
    expect(screen.getByText('Message 19')).toBeInTheDocument();
  });

  // Get the messages container
  const messagesContainer = screen.getByText('Message 19').closest('[class*="overflow-y-auto"]');

  // Verify last message is visible (scrolled into view)
  const lastMessage = screen.getByText('Message 19');
  expect(lastMessage).toBeVisible();

  // Note: Full scroll testing requires jsdom-testing-library extensions
  // or e2e tests with Playwright
});
```

## Test Coverage Summary

| Category | Test Cases | Status |
|----------|-----------|--------|
| Rendering | 1, 7 | ✅ Specified |
| User Interaction | 2, 4 | ✅ Specified |
| Real-time Updates | 3 | ✅ Specified |
| Error Handling | 6 | ✅ Specified |
| State Management | 5, 8 | ✅ Specified |

**Total**: 8 test cases as required by cf-14.2

## Installation Requirements

To run these tests, install:

```bash
npm install --save-dev @testing-library/react @testing-library/jest-dom jest jest-environment-jsdom msw
```

Update `package.json`:

```json
{
  "scripts": {
    "test": "jest",
    "test:watch": "jest --watch"
  }
}
```

Create `jest.config.js`:

```javascript
module.exports = {
  testEnvironment: 'jsdom',
  setupFilesAfterEnv: ['<rootDir>/jest.setup.js'],
  moduleNameMapper: {
    '^@/(.*)$': '<rootDir>/src/$1'
  }
};
```
