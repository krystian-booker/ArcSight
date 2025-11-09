from flask import Blueprint

settings = Blueprint("settings", __name__, url_prefix="/settings")

from . import routes as routes  # noqa: E402, F401
from . import api_routes as api_routes  # noqa: E402, F401
