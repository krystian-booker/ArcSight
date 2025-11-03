/**
 * WebSocket service for real-time video streaming
 * Handles MSE (Media Source Extensions) video streaming via WebSocket
 */

type VideoStreamCallback = (frameData: ArrayBuffer) => void;
type ConnectionCallback = (connected: boolean) => void;
type ErrorCallback = (error: Error) => void;

interface StreamSubscription {
  id: string;
  onFrame: VideoStreamCallback;
  onConnectionChange?: ConnectionCallback;
  onError?: ErrorCallback;
}

class WebSocketService {
  private ws: WebSocket | null = null;
  private subscriptions: Map<string, StreamSubscription> = new Map();
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectDelay = 1000; // ms
  private reconnectTimer: number | null = null;
  private isConnecting = false;

  /**
   * Connect to WebSocket server
   */
  private connect(): void {
    if (this.ws?.readyState === WebSocket.OPEN || this.isConnecting) {
      return;
    }

    this.isConnecting = true;
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws`;

    try {
      this.ws = new WebSocket(wsUrl);
      this.ws.binaryType = 'arraybuffer';

      this.ws.onopen = () => {
        console.log('WebSocket connected');
        this.isConnecting = false;
        this.reconnectAttempts = 0;
        this.notifyConnectionChange(true);
      };

      this.ws.onmessage = (event) => {
        if (event.data instanceof ArrayBuffer) {
          // Binary frame data - forward to all subscribers
          this.subscriptions.forEach((sub) => {
            try {
              sub.onFrame(event.data);
            } catch (error) {
              console.error('Error in frame callback:', error);
              sub.onError?.(error as Error);
            }
          });
        }
      };

      this.ws.onerror = (event) => {
        console.error('WebSocket error:', event);
        this.isConnecting = false;
        this.notifyError(new Error('WebSocket connection error'));
      };

      this.ws.onclose = () => {
        console.log('WebSocket closed');
        this.isConnecting = false;
        this.ws = null;
        this.notifyConnectionChange(false);
        this.attemptReconnect();
      };
    } catch (error) {
      console.error('Failed to create WebSocket:', error);
      this.isConnecting = false;
      this.notifyError(error as Error);
    }
  }

  /**
   * Attempt to reconnect with exponential backoff
   */
  private attemptReconnect(): void {
    if (this.subscriptions.size === 0) {
      // No active subscriptions, don't reconnect
      return;
    }

    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.error('Max reconnect attempts reached');
      this.notifyError(new Error('Failed to reconnect to video stream'));
      return;
    }

    const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts);
    console.log(`Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts + 1}/${this.maxReconnectAttempts})`);

    this.reconnectTimer = window.setTimeout(() => {
      this.reconnectAttempts++;
      this.connect();
    }, delay);
  }

  /**
   * Subscribe to video stream
   */
  subscribe(
    streamId: string,
    onFrame: VideoStreamCallback,
    onConnectionChange?: ConnectionCallback,
    onError?: ErrorCallback
  ): () => void {
    const subscription: StreamSubscription = {
      id: streamId,
      onFrame,
      onConnectionChange,
      onError,
    };

    this.subscriptions.set(streamId, subscription);

    // Connect if not already connected
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      this.connect();
    } else {
      // Already connected, notify immediately
      onConnectionChange?.(true);
    }

    // Send subscription message to server
    this.sendMessage({
      type: 'subscribe',
      stream_id: streamId,
    });

    // Return unsubscribe function
    return () => {
      this.unsubscribe(streamId);
    };
  }

  /**
   * Unsubscribe from video stream
   */
  private unsubscribe(streamId: string): void {
    this.subscriptions.delete(streamId);

    // Send unsubscribe message to server
    this.sendMessage({
      type: 'unsubscribe',
      stream_id: streamId,
    });

    // Close connection if no more subscriptions
    if (this.subscriptions.size === 0) {
      this.disconnect();
    }
  }

  /**
   * Send message to server
   */
  private sendMessage(message: any): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(message));
    }
  }

  /**
   * Disconnect WebSocket
   */
  private disconnect(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }

    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }

    this.reconnectAttempts = 0;
  }

  /**
   * Notify all subscribers of connection change
   */
  private notifyConnectionChange(connected: boolean): void {
    this.subscriptions.forEach((sub) => {
      sub.onConnectionChange?.(connected);
    });
  }

  /**
   * Notify all subscribers of error
   */
  private notifyError(error: Error): void {
    this.subscriptions.forEach((sub) => {
      sub.onError?.(error);
    });
  }

  /**
   * Get connection status
   */
  isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }
}

// Export singleton instance
export const websocketService = new WebSocketService();

// Helper functions for common stream types
export function subscribeToRawFeed(
  cameraId: number,
  onFrame: VideoStreamCallback,
  onConnectionChange?: ConnectionCallback,
  onError?: ErrorCallback
): () => void {
  return websocketService.subscribe(
    `raw_${cameraId}`,
    onFrame,
    onConnectionChange,
    onError
  );
}

export function subscribeToProcessedFeed(
  pipelineId: number,
  onFrame: VideoStreamCallback,
  onConnectionChange?: ConnectionCallback,
  onError?: ErrorCallback
): () => void {
  return websocketService.subscribe(
    `processed_${pipelineId}`,
    onFrame,
    onConnectionChange,
    onError
  );
}

export function subscribeToCalibrationFeed(
  cameraId: number,
  onFrame: VideoStreamCallback,
  onConnectionChange?: ConnectionCallback,
  onError?: ErrorCallback
): () => void {
  return websocketService.subscribe(
    `calibration_${cameraId}`,
    onFrame,
    onConnectionChange,
    onError
  );
}
