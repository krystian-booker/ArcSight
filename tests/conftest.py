import pytest
from app import create_app, db

@pytest.fixture(scope='module')
def app():
    """
    Creates a test Flask application instance with testing-specific configuration.
    """
    config_overrides = {
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "CAMERA_THREADS_ENABLED": False,
        "SERVER_NAME": "localhost.localdomain",  # Required for url_for to work in tests
        "WTF_CSRF_ENABLED": False  # Disable CSRF for tests
    }
    app = create_app(config_overrides)

    with app.app_context():
        db.create_all()
        engine = db.engine
        try:
            yield app
        finally:
            db.session.remove()
            db.drop_all()
            engine.dispose()

@pytest.fixture()
def client(app):
    """A test client for the app."""
    with app.app_context():
        yield app.test_client()

@pytest.fixture()
def runner(app):
    """A test runner for the app's Click commands."""
    return app.test_cli_runner()