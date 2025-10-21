from flask import Blueprint

monitoring = Blueprint("monitoring", __name__)

from . import routes  # noqa: E402, F401
