"""React App blueprint for serving the React frontend."""

from flask import Blueprint, send_from_directory, current_app
import os

bp = Blueprint('react_app', __name__)


@bp.route('/', defaults={'path': ''})
@bp.route('/<path:path>')
def serve_react_app(path):
    """
    Serve React app for all routes except API routes.

    This allows React Router to handle client-side routing while
    Flask serves the static build files.
    """
    react_build_dir = os.path.join(
        current_app.static_folder,
        'react_build'
    )

    # Check if build directory exists
    if not os.path.exists(react_build_dir):
        return (
            "React app not built yet. Please run 'cd frontend && npm run build' "
            "or use 'npm run dev' for development mode.",
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
