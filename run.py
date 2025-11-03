"""Application entry point.

Run the Flask application with environment-based configuration.

Environment Variables:
    FLASK_ENV: Set to 'development' for debug mode, 'production' for production
    FLASK_DEBUG: Set to '1' to enable debug mode (alternative to FLASK_ENV)
    HOST: Server host address (default: 0.0.0.0)
    PORT: Server port (default: 8080)
    VITE_AUTO_START: Set to '0' to disable auto-starting Vite in development

Examples:
    # Production mode (default)
    python run.py

    # Development mode with debug
    FLASK_ENV=development python run.py

    # Or using FLASK_DEBUG
    FLASK_DEBUG=1 python run.py

    # Development without auto-starting Vite
    FLASK_ENV=development VITE_AUTO_START=0 python run.py
"""

import socket
import sys
from app import create_app
from app.vite_manager import get_vite_manager

app = create_app()
socketio = app.socketio  # Get SocketIO instance from app

if __name__ == "__main__":
    # Get configuration from app.config (set by config.py)
    host = app.config.get('HOST', '0.0.0.0')
    port = app.config.get('PORT', 8080)
    debug = app.config.get('DEBUG', False)
    vite_auto_start = app.config.get('VITE_AUTO_START', False)
    vite_url = app.config.get('VITE_DEV_SERVER_URL', 'http://localhost:5173')

    # Display server information
    print("\n" + "="*60)
    print("ArcSight Server Starting")
    print("="*60)

    # Get local IP addresses
    hostname = socket.gethostname()
    try:
        local_ip = socket.gethostbyname(hostname)
        print(f"Local IP: http://{local_ip}:{port}")
    except:
        pass

    if host == '0.0.0.0':
        print(f"Listening on all interfaces: http://0.0.0.0:{port}")
        print(f"Localhost: http://127.0.0.1:{port}")
        print(f"Hostname: http://{hostname}:{port}")
    else:
        print(f"Server: http://{host}:{port}")

    print(f"Mode: {'DEBUG' if debug else 'PRODUCTION'}")
    print(f"WebSocket: Enabled")

    # Start Vite dev server in development mode
    vite_manager = None
    if debug and vite_auto_start:
        print(f"Frontend: Vite dev server (auto-start)")
        vite_manager = get_vite_manager(vite_url)
        if not vite_manager.start():
            print("\nERROR: Failed to start Vite dev server")
            print("You can either:")
            print("  1. Fix the issue and restart Flask")
            print("  2. Start Vite manually: cd frontend && npm run dev")
            print("  3. Disable auto-start: VITE_AUTO_START=0 python run.py")
            sys.exit(1)
    elif debug:
        print(f"Frontend: Vite dev server (manual start at {vite_url})")
    else:
        print(f"Frontend: Static build (app/static/react_build)")

    print("="*60 + "\n")

    try:
        # IMPORTANT: use_reloader=False to prevent issues with camera threads
        # The reloader would spawn duplicate threads and cause resource conflicts
        # Use socketio.run() instead of app.run() for WebSocket support
        socketio.run(app, host=host, port=port, debug=debug, use_reloader=False, allow_unsafe_werkzeug=True)
    finally:
        # Clean up Vite process on exit
        if vite_manager:
            vite_manager.stop()
