/**
 * WebSocket client for real-time updates
 */

import type { WebSocketMessage } from '@/types';

const WS_BASE_URL = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8080/ws';

/**
 * Get the WebSocket URL with authentication token
 * The backend requires token as a query parameter for authentication
 */
function getAuthenticatedWsUrl(): string {
  const token = typeof window !== 'undefined' ? localStorage.getItem('auth_token') : null;
  if (token) {
    return `${WS_BASE_URL}?token=${encodeURIComponent(token)}`;
  }
  return WS_BASE_URL;
}

export class WebSocketClient {
  private ws: WebSocket | null = null;
  private reconnectTimeout: NodeJS.Timeout | null = null;
  private messageHandlers: Set<(message: WebSocketMessage) => void> = new Set();
  private reconnectHandlers: Set<() => void> = new Set();
  private connectionHandlers: Set<(connected: boolean) => void> = new Set();
  private reconnectAttempts: number = 0;
  private maxReconnectAttempts: number = 10;
  private baseReconnectDelay: number = 1000; // 1 second
  private maxReconnectDelay: number = 30000; // 30 seconds
  private lastReconnectTime: number = 0;
  private minReconnectInterval: number = 500; // Minimum 500ms between reconnects (debounce)

  connect() {
    if (this.ws?.readyState === WebSocket.OPEN) {
      return;
    }

    const wsUrl = getAuthenticatedWsUrl();
    this.ws = new WebSocket(wsUrl);

    this.ws.onopen = () => {
      console.log('WebSocket connected');

      // Reset reconnect attempts on successful connection
      this.reconnectAttempts = 0;

      if (this.reconnectTimeout) {
        clearTimeout(this.reconnectTimeout);
        this.reconnectTimeout = null;
        // Notify reconnect handlers
        this.notifyReconnect();
      }
      // Notify connection change
      this.notifyConnectionChange(true);
    };

    this.ws.onmessage = (event) => {
      try {
        const message: WebSocketMessage = JSON.parse(event.data);
        this.messageHandlers.forEach((handler) => handler(message));
      } catch (error) {
        console.error('Failed to parse WebSocket message:', error);
      }
    };

    this.ws.onclose = () => {
      console.log('WebSocket disconnected, reconnecting...');
      this.notifyConnectionChange(false);
      this.reconnect();
    };

    this.ws.onerror = (error) => {
      console.error('WebSocket error:', error);
    };
  }

  disconnect() {
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout);
      this.reconnectTimeout = null;
    }
  }

  /**
   * Reconnect with exponential backoff and debounce (T093-T094)
   *
   * Implements:
   * - Exponential backoff: delay doubles with each attempt (1s, 2s, 4s, 8s, 16s, 30s max)
   * - Max attempts: stops after 10 failed attempts
   * - Debounce: minimum 500ms between reconnection attempts
   */
  private reconnect() {
    // Debounce: Prevent rapid reconnect cycles (T094)
    const now = Date.now();
    const timeSinceLastReconnect = now - this.lastReconnectTime;
    if (timeSinceLastReconnect < this.minReconnectInterval) {
      if (process.env.NODE_ENV === 'development') {
        console.log('Reconnect debounced, too soon since last attempt');
      }
      return;
    }

    // Check max attempts
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.error(
        `WebSocket failed to reconnect after ${this.maxReconnectAttempts} attempts`
      );
      return;
    }

    // Calculate exponential backoff delay (T093)
    // Formula: baseDelay * 2^attempts, capped at maxDelay
    const delay = Math.min(
      this.baseReconnectDelay * Math.pow(2, this.reconnectAttempts),
      this.maxReconnectDelay
    );

    if (process.env.NODE_ENV === 'development') {
      console.log(
        `Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts + 1}/${this.maxReconnectAttempts})`
      );
    }

    this.reconnectTimeout = setTimeout(() => {
      this.reconnectAttempts++;
      this.lastReconnectTime = Date.now();
      this.connect();
    }, delay);
  }

  subscribe(projectId: number) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(
        JSON.stringify({
          type: 'subscribe',
          project_id: projectId,
        })
      );
    }
  }

  onMessage(handler: (message: WebSocketMessage) => void) {
    this.messageHandlers.add(handler);
    return () => this.messageHandlers.delete(handler);
  }

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
  send(message: any) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(message));
    }
  }

  /**
   * Register a callback to be called when WebSocket reconnects
   */
  onReconnect(handler: () => void) {
    this.reconnectHandlers.add(handler);
    return () => this.reconnectHandlers.delete(handler);
  }

  /**
   * Register a callback to be called when connection status changes
   */
  onConnectionChange(handler: (connected: boolean) => void) {
    this.connectionHandlers.add(handler);
    return () => this.connectionHandlers.delete(handler);
  }

  /**
   * Notify all connection change handlers
   */
  private notifyConnectionChange(connected: boolean) {
    this.connectionHandlers.forEach((handler) => handler(connected));
  }

  /**
   * Notify all reconnect handlers
   */
  private notifyReconnect() {
    this.reconnectHandlers.forEach((handler) => handler());
  }
}

// Singleton instance
let wsClient: WebSocketClient | null = null;

export function getWebSocketClient(): WebSocketClient {
  if (!wsClient) {
    wsClient = new WebSocketClient();
  }
  return wsClient;
}
