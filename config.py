"""Flask application configuration.

This module provides environment-based configuration for the Flask application.
Configuration is loaded from environment variables with sensible defaults.

Environment Variables:
    FLASK_ENV: Application environment (development, production, testing)
    FLASK_DEBUG: Enable Flask debug mode (0 or 1)
    DATABASE_URL: SQLAlchemy database URI
    HOST: Server host address (default: 0.0.0.0)
    PORT: Server port (default: 8080)
"""

import os


class Config:
    """Base configuration with defaults suitable for production."""

    # Flask core settings
    DEBUG = False
    TESTING = False

    # Server settings
    HOST = os.environ.get('HOST', '0.0.0.0')
    PORT = int(os.environ.get('PORT', 8080))

    # Database settings
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Application settings
    CAMERA_THREADS_ENABLED = True
    BRAND_NAME = os.environ.get('BRAND_NAME', 'ArcSight')
    BRAND_TAGLINE = os.environ.get('BRAND_TAGLINE', 'Industrial computer vision, engineered in the open.')
    METRICS_ENABLED = os.environ.get('METRICS_ENABLED', '1').lower() not in ('0', 'false', 'no')
    METRICS_WINDOW_SECONDS = float(os.environ.get('METRICS_WINDOW_SECONDS', 300))
    METRICS_FPS_WINDOW_SECONDS = float(os.environ.get('METRICS_FPS_WINDOW_SECONDS', 10))
    METRICS_MEMORY_SAMPLE_SECONDS = float(os.environ.get('METRICS_MEMORY_SAMPLE_SECONDS', 2))
    PIPELINE_QUEUE_HIGH_UTILIZATION_PCT = float(os.environ.get('PIPELINE_QUEUE_HIGH_UTILIZATION_PCT', 80))
    PIPELINE_LATENCY_WARN_MS = float(os.environ.get('PIPELINE_LATENCY_WARN_MS', 150))
    METRICS_REFRESH_INTERVAL_MS = int(os.environ.get('METRICS_REFRESH_INTERVAL_MS', 2000))

    # Vite/React development settings
    VITE_DEV_SERVER_URL = os.environ.get('VITE_DEV_SERVER_URL', 'http://localhost:5173')
    VITE_AUTO_START = os.environ.get('VITE_AUTO_START', '1').lower() not in ('0', 'false', 'no')


class DevelopmentConfig(Config):
    """Development configuration with debug enabled and verbose logging."""

    DEBUG = True
    # In development, we might want to see detailed errors
    # but still disable the reloader for camera thread stability
    ENV = 'development'
    # Auto-start Vite in development mode
    VITE_AUTO_START = os.environ.get('VITE_AUTO_START', '1').lower() not in ('0', 'false', 'no')


class ProductionConfig(Config):
    """Production configuration - secure and optimized."""

    DEBUG = False
    ENV = 'production'


class TestingConfig(Config):
    """Testing configuration with in-memory database."""

    TESTING = True
    DEBUG = False
    # Use in-memory SQLite for tests
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    # Disable camera threads in tests
    CAMERA_THREADS_ENABLED = False
    METRICS_ENABLED = False
    # Don't auto-start Vite in tests (Playwright handles this)
    VITE_AUTO_START = False


# Configuration dictionary
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': ProductionConfig  # Default to production for safety
}


def get_config():
    """Get the appropriate configuration based on environment.

    Returns:
        Config: Configuration class based on FLASK_ENV or FLASK_DEBUG

    Priority:
        1. FLASK_ENV environment variable
        2. FLASK_DEBUG environment variable (0/1)
        3. Default to production (safe default)
    """
    # Check FLASK_ENV first
    env = os.environ.get('FLASK_ENV', '').lower()
    if env in config:
        return config[env]

    # Fall back to FLASK_DEBUG
    debug = os.environ.get('FLASK_DEBUG', '0').lower()
    if debug in ('1', 'true', 'yes', 'on'):
        return config['development']

    # Default to production (safe default)
    return config['default']
