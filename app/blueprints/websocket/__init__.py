"""
WebSocket blueprint for real-time video streaming.

This blueprint provides WebSocket-based video streaming with MSE support,
offering more efficient streaming than MJPEG for React frontend.
"""

from flask import Blueprint
from flask_socketio import SocketIO, emit, join_room, leave_room
import logging
import threading
from typing import Dict, Set
import time

logger = logging.getLogger(__name__)

# Global SocketIO instance (will be initialized in create_app)
socketio = None

# Track active subscriptions: {stream_id: set of session IDs}
active_subscriptions: Dict[str, Set[str]] = {}
subscriptions_lock = threading.Lock()


def init_socketio(app):
    """
    Initialize Flask-SocketIO with the Flask app.

    Args:
        app: Flask application instance

    Returns:
        SocketIO instance
    """
    global socketio

    socketio = SocketIO(
        app,
        cors_allowed_origins="*",  # Allow all origins for development
        async_mode='threading',    # Use threading mode for compatibility
        logger=app.debug,
        engineio_logger=app.debug,
        ping_timeout=60,
        ping_interval=25,
    )

    # Register event handlers
    @socketio.on('connect')
    def handle_connect():
        """Handle client connection"""
        from flask import request
        logger.info(f"WebSocket client connected: {request.sid}")
        emit('connected', {'status': 'success'})

    @socketio.on('disconnect')
    def handle_disconnect():
        """Handle client disconnection and cleanup subscriptions"""
        from flask import request
        sid = request.sid
        logger.info(f"WebSocket client disconnected: {sid}")

        # Clean up all subscriptions for this client
        with subscriptions_lock:
            for stream_id in list(active_subscriptions.keys()):
                if sid in active_subscriptions[stream_id]:
                    active_subscriptions[stream_id].discard(sid)
                    leave_room(stream_id, sid=sid)
                    logger.debug(f"Removed {sid} from stream {stream_id}")

                    # Clean up empty subscription sets
                    if not active_subscriptions[stream_id]:
                        del active_subscriptions[stream_id]

    @socketio.on('subscribe')
    def handle_subscribe(data):
        """
        Handle subscription to a video stream.

        Message format:
        {
            "type": "subscribe",
            "stream_id": "raw_1" | "processed_5" | "calibration_2"
        }
        """
        from flask import request
        stream_id = data.get('stream_id')
        sid = request.sid

        if not stream_id:
            emit('error', {'message': 'stream_id is required'})
            return

        # Add to subscriptions
        with subscriptions_lock:
            if stream_id not in active_subscriptions:
                active_subscriptions[stream_id] = set()
            active_subscriptions[stream_id].add(sid)

        # Join room for this stream
        join_room(stream_id, sid=sid)

        logger.info(f"Client {sid} subscribed to stream {stream_id}")
        emit('subscribed', {'stream_id': stream_id, 'status': 'success'})

    @socketio.on('unsubscribe')
    def handle_unsubscribe(data):
        """
        Handle unsubscription from a video stream.

        Message format:
        {
            "type": "unsubscribe",
            "stream_id": "raw_1"
        }
        """
        from flask import request
        stream_id = data.get('stream_id')
        sid = request.sid

        if not stream_id:
            emit('error', {'message': 'stream_id is required'})
            return

        # Remove from subscriptions
        with subscriptions_lock:
            if stream_id in active_subscriptions:
                active_subscriptions[stream_id].discard(sid)
                if not active_subscriptions[stream_id]:
                    del active_subscriptions[stream_id]

        # Leave room
        leave_room(stream_id, sid=sid)

        logger.info(f"Client {sid} unsubscribed from stream {stream_id}")
        emit('unsubscribed', {'stream_id': stream_id, 'status': 'success'})

    @socketio.on('request_keyframe')
    def handle_keyframe_request(data):
        """
        Handle request for keyframe (for MSE).

        Clients can request a keyframe to recover from decoding errors.
        """
        from flask import request
        stream_id = data.get('stream_id')
        sid = request.sid

        logger.debug(f"Keyframe requested for stream {stream_id} by {sid}")
        # TODO: Signal encoder to generate keyframe
        emit('keyframe_pending', {'stream_id': stream_id})

    return socketio


def broadcast_frame(stream_id: str, frame_data: bytes, metadata: dict = None):
    """
    Broadcast video frame to all subscribers of a stream.

    Args:
        stream_id: Stream identifier (e.g., "raw_1", "processed_5")
        frame_data: Encoded frame data (JPEG, H.264, etc.)
        metadata: Optional metadata (timestamp, frame_number, etc.)
    """
    if socketio is None:
        logger.warning("SocketIO not initialized, cannot broadcast frame")
        return

    with subscriptions_lock:
        subscriber_count = len(active_subscriptions.get(stream_id, set()))

    # Only broadcast if there are subscribers
    if subscriber_count > 0:
        payload = {
            'stream_id': stream_id,
            'timestamp': time.time(),
        }

        if metadata:
            payload.update(metadata)

        # Emit to room (all subscribers)
        socketio.emit(
            'frame',
            payload,
            room=stream_id,
            namespace='/',
            binary=True,
            include_self=False
        )


def get_subscriber_count(stream_id: str) -> int:
    """Get number of active subscribers for a stream"""
    with subscriptions_lock:
        return len(active_subscriptions.get(stream_id, set()))


def is_stream_active(stream_id: str) -> bool:
    """Check if a stream has any active subscribers"""
    return get_subscriber_count(stream_id) > 0
