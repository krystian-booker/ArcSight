"""Test script to verify configuration works in different modes.

This script tests that the configuration system properly handles
development and production modes.
"""

import os
import sys

def test_production_mode():
    """Test production configuration (default)."""
    print("=" * 70)
    print("TEST 1: Production Mode (Default)")
    print("=" * 70)

    # Clear any existing FLASK_ environment variables
    for key in list(os.environ.keys()):
        if key.startswith('FLASK_'):
            del os.environ[key]

    from config import get_config
    config = get_config()

    print(f"Config class: {config.__name__}")
    print(f"DEBUG: {config.DEBUG}")
    print(f"ENV: {getattr(config, 'ENV', 'N/A')}")
    print(f"HOST: {config.HOST}")
    print(f"PORT: {config.PORT}")

    assert config.DEBUG == False, "Production mode should have DEBUG=False"
    assert config.__name__ == 'ProductionConfig', "Should use ProductionConfig"
    print("[PASS] Production mode test PASSED\n")


def test_development_mode_via_flask_env():
    """Test development configuration via FLASK_ENV."""
    print("=" * 70)
    print("TEST 2: Development Mode (FLASK_ENV=development)")
    print("=" * 70)

    # Set FLASK_ENV
    os.environ['FLASK_ENV'] = 'development'

    # Need to reload config module to pick up new env vars
    if 'config' in sys.modules:
        del sys.modules['config']

    from config import get_config
    config = get_config()

    print(f"Config class: {config.__name__}")
    print(f"DEBUG: {config.DEBUG}")
    print(f"ENV: {getattr(config, 'ENV', 'N/A')}")

    assert config.DEBUG == True, "Development mode should have DEBUG=True"
    assert config.__name__ == 'DevelopmentConfig', "Should use DevelopmentConfig"
    print("[PASS] Development mode (FLASK_ENV) test PASSED\n")

    # Cleanup
    del os.environ['FLASK_ENV']


def test_development_mode_via_flask_debug():
    """Test development configuration via FLASK_DEBUG."""
    print("=" * 70)
    print("TEST 3: Development Mode (FLASK_DEBUG=1)")
    print("=" * 70)

    # Set FLASK_DEBUG
    os.environ['FLASK_DEBUG'] = '1'

    # Need to reload config module to pick up new env vars
    if 'config' in sys.modules:
        del sys.modules['config']

    from config import get_config
    config = get_config()

    print(f"Config class: {config.__name__}")
    print(f"DEBUG: {config.DEBUG}")
    print(f"ENV: {getattr(config, 'ENV', 'N/A')}")

    assert config.DEBUG == True, "FLASK_DEBUG=1 should enable debug"
    assert config.__name__ == 'DevelopmentConfig', "Should use DevelopmentConfig"
    print("[PASS] Development mode (FLASK_DEBUG) test PASSED\n")

    # Cleanup
    del os.environ['FLASK_DEBUG']


def test_app_creation():
    """Test that Flask app can be created with both configs."""
    print("=" * 70)
    print("TEST 4: Flask App Creation")
    print("=" * 70)

    # Clear environment
    for key in list(os.environ.keys()):
        if key.startswith('FLASK_'):
            del os.environ[key]

    # Reload modules
    for mod in ['config', 'app', 'app.extensions']:
        if mod in sys.modules:
            del sys.modules[mod]

    from app import create_app

    # Test with test config override
    app = create_app({'TESTING': True, 'CAMERA_THREADS_ENABLED': False})

    print(f"App created: {app.name}")
    print(f"App DEBUG: {app.config['DEBUG']}")
    print(f"App TESTING: {app.config['TESTING']}")
    print(f"Camera threads enabled: {app.config['CAMERA_THREADS_ENABLED']}")

    assert app.config['TESTING'] == True, "Test override should work"
    assert app.config['CAMERA_THREADS_ENABLED'] == False, "Test override should work"
    print("[PASS] Flask app creation test PASSED\n")


if __name__ == '__main__':
    print("\n" + "=" * 70)
    print("CONFIGURATION SYSTEM TESTS")
    print("=" * 70 + "\n")

    try:
        test_production_mode()
        test_development_mode_via_flask_env()
        test_development_mode_via_flask_debug()
        test_app_creation()

        print("=" * 70)
        print("*** ALL TESTS PASSED! ***")
        print("=" * 70)
        print("\nConfiguration system is working correctly!")
        print("Default mode: Production (DEBUG=False)")
        print("Development mode: Set FLASK_ENV=development or FLASK_DEBUG=1")

    except AssertionError as e:
        print(f"\n[FAIL] TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
