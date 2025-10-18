from flask import Blueprint

cameras = Blueprint("cameras", __name__, url_prefix="/cameras")

from . import routes as routes  # noqa: E402, F401
