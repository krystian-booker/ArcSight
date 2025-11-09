"""
Legacy settings routes (deprecated).

The settings page has been migrated to React.
Old form-based routes have been replaced with REST API endpoints in api_routes.py.

This file is kept for backward compatibility but all routes redirect to the React app.
"""

import logging
from flask import redirect
from . import settings

logger = logging.getLogger(__name__)


@settings.route("/")
def settings_page():
    """
    Legacy settings page route.

    The settings page has been migrated to React and is served by the react_app blueprint.
    This route is kept for backward compatibility and redirects to the root,
    which the react_app blueprint will handle.
    """
    # The react_app blueprint (registered last) will catch this and serve the React app
    # We don't need to redirect - just let Flask continue to the next blueprint
    return redirect("/settings")
