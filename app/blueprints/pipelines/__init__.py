from flask import Blueprint

pipelines = Blueprint("pipelines", __name__, url_prefix="/api")

from . import routes as routes  # noqa: E402, F401
