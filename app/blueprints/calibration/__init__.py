from flask import Blueprint

calibration = Blueprint('calibration', __name__, url_prefix='/calibration')

from . import routes