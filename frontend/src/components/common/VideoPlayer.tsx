/**
 * VideoPlayer component for real-time video streaming
 * Receives JPEG frames via WebSocket and displays them
 */

import { useEffect, useRef, useState } from 'react';
import { websocketService } from '@/services';
import Spinner from './Spinner';

export type StreamType = 'raw' | 'processed' | 'calibration';

interface VideoPlayerProps {
  cameraId?: number;
  pipelineId?: number;
  streamType: StreamType;
  className?: string;
  showStatus?: boolean;
  onError?: (error: Error) => void;
}

export default function VideoPlayer({
  cameraId,
  pipelineId,
  streamType,
  className = '',
  showStatus = true,
  onError,
}: VideoPlayerProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [hasReceivedFrame, setHasReceivedFrame] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fps, setFps] = useState(0);
  const fpsCounterRef = useRef({ frames: 0, lastTime: Date.now() });

  useEffect(() => {
    // Determine stream ID based on type
    let streamId: string;
    if (streamType === 'raw' && cameraId !== undefined) {
      streamId = `raw_${cameraId}`;
    } else if (streamType === 'processed' && pipelineId !== undefined) {
      streamId = `processed_${pipelineId}`;
    } else if (streamType === 'calibration' && cameraId !== undefined) {
      streamId = `calibration_${cameraId}`;
    } else {
      setError('Invalid stream configuration');
      return;
    }

    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) {
      setError('Failed to get canvas context');
      return;
    }

    // Handle frame data
    const handleFrame = (frameData: ArrayBuffer) => {
      try {
        // Convert ArrayBuffer to Blob
        const blob = new Blob([frameData], { type: 'image/jpeg' });
        const url = URL.createObjectURL(blob);

        // Create image and draw to canvas
        const img = new Image();
        img.onload = () => {
          // Resize canvas to match image dimensions
          if (canvas.width !== img.width || canvas.height !== img.height) {
            canvas.width = img.width;
            canvas.height = img.height;
          }

          // Draw frame
          ctx.drawImage(img, 0, 0);
          URL.revokeObjectURL(url);

          // Mark that we've received at least one frame
          if (!hasReceivedFrame) {
            setHasReceivedFrame(true);
          }

          // Update FPS counter
          const counter = fpsCounterRef.current;
          counter.frames++;
          const now = Date.now();
          const elapsed = now - counter.lastTime;
          if (elapsed >= 1000) {
            setFps(Math.round((counter.frames * 1000) / elapsed));
            counter.frames = 0;
            counter.lastTime = now;
          }
        };

        img.onerror = () => {
          URL.revokeObjectURL(url);
          console.error('Failed to decode frame');
        };

        img.src = url;
      } catch (err) {
        console.error('Error handling frame:', err);
      }
    };

    // Handle connection changes
    const handleConnectionChange = (connected: boolean) => {
      setIsConnected(connected);
      if (!connected) {
        setHasReceivedFrame(false);
        setFps(0);
      }
    };

    // Handle errors
    const handleError = (err: Error) => {
      console.error('Video stream error:', err);
      setError(err.message);
      onError?.(err);
    };

    // Subscribe to stream
    const unsubscribe = websocketService.subscribe(
      streamId,
      handleFrame,
      handleConnectionChange,
      handleError
    );

    // Cleanup on unmount
    return () => {
      unsubscribe();
      setHasReceivedFrame(false);
      setIsConnected(false);
      setFps(0);
    };
  }, [cameraId, pipelineId, streamType, hasReceivedFrame, onError]);

  return (
    <div className={`relative bg-arc-surface rounded-arc-sm overflow-hidden ${className}`}>
      {/* Canvas for video display */}
      <canvas
        ref={canvasRef}
        className="w-full h-full object-contain"
        style={{ display: hasReceivedFrame ? 'block' : 'none' }}
      />

      {/* Loading state */}
      {!hasReceivedFrame && !error && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-md text-arc-muted">
          <Spinner size="lg" />
          <p className="text-sm">
            {isConnected ? 'Waiting for video stream...' : 'Connecting to stream...'}
          </p>
        </div>
      )}

      {/* Error state */}
      {error && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-sm text-arc-danger p-lg text-center">
          <svg
            className="w-12 h-12"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
            xmlns="http://www.w3.org/2000/svg"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
            />
          </svg>
          <p className="text-sm font-medium">Video Stream Error</p>
          <p className="text-xs text-arc-subtle">{error}</p>
        </div>
      )}

      {/* Status overlay */}
      {showStatus && hasReceivedFrame && (
        <div className="absolute top-sm left-sm flex items-center gap-xs">
          {/* Connection status indicator */}
          <div
            className={`
              h-2 w-2 rounded-full
              ${isConnected ? 'bg-arc-success animate-pulse' : 'bg-arc-danger'}
            `}
          />
          {/* FPS counter */}
          <span className="text-xs font-mono text-arc-muted bg-black bg-opacity-50 px-xs py-3xs rounded">
            {fps} FPS
          </span>
        </div>
      )}
    </div>
  );
}
