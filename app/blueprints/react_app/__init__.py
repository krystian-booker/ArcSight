"""React App blueprint for serving the React frontend."""

from flask import Blueprint, send_from_directory, current_app, request
import os
import requests

bp = Blueprint('react_app', __name__)


def _proxy_to_vite(path):
    """Proxy request to Vite dev server.

    Args:
        path: Request path

    Returns:
        Response from Vite dev server or error message
    """
    vite_url = current_app.config.get('VITE_DEV_SERVER_URL', 'http://localhost:5173')
    target_url = f"{vite_url}/{path}" if path else vite_url

    try:
        # Forward the request to Vite
        resp = requests.get(
            target_url,
            headers={k: v for k, v in request.headers if k.lower() != 'host'},
            timeout=5
        )

        # Return the response from Vite
        return resp.content, resp.status_code, resp.headers.items()

    except requests.exceptions.ConnectionError:
        return (
            f"Cannot connect to Vite dev server at {vite_url}. "
            "Please ensure Vite is running with 'cd frontend && npm run dev'",
            503
        )
    except Exception as e:
        return f"Error proxying to Vite: {str(e)}", 500


@bp.route('/', defaults={'path': ''})
@bp.route('/<path:path>')
def serve_react_app(path):
    """
    Serve React app for all routes except API routes.

    In development mode: Proxies to Vite dev server for HMR and client-side routing
    In production mode: Serves static build files from react_build directory

    This allows React Router to handle client-side routing.
    """
    # Check if we're in development mode with Vite
    is_development = current_app.config.get('DEBUG', False)
    vite_url = current_app.config.get('VITE_DEV_SERVER_URL', 'http://localhost:5173')

    if is_development:
        # In development, proxy to Vite dev server
        return _proxy_to_vite(path)

    # Production mode - serve static build files
    # Get the absolute path to frontend/dist directory
    app_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    project_root = os.path.dirname(app_root)
    react_build_dir = os.path.join(project_root, 'frontend', 'dist')

    # Check if build directory exists
    if not os.path.exists(react_build_dir):
        return (
            "React app not built yet. Please run 'cd frontend && npm run build' "
            "to build the production bundle.",
            503
        )

    # If path is a file that exists, serve it
    if path and os.path.exists(os.path.join(react_build_dir, path)):
        return send_from_directory(react_build_dir, path)

    # Otherwise, serve index.html (for React Router)
    index_path = os.path.join(react_build_dir, 'index.html')
    if os.path.exists(index_path):
        return send_from_directory(react_build_dir, 'index.html')

    return "React app not found. Please build the frontend first.", 404
