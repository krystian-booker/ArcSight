"""
Test mock blueprint for E2E testing
Provides mock camera devices and video feeds for Playwright tests
"""
from flask import Blueprint

test_mock = Blueprint("test_mock", __name__, url_prefix="/test")

from . import routes
