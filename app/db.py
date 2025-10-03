import sqlite3
import os
import json
from appdirs import user_data_dir
from flask import g

APP_NAME = "VisionTools"
APP_AUTHOR = "User"

data_dir = user_data_dir(APP_NAME, APP_AUTHOR)
os.makedirs(data_dir, exist_ok=True)
DB_PATH = os.path.join(data_dir, "config.db")


def get_db():
    """Gets the current database connection, or creates a new one if none exists."""
    if 'db' not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(e=None):
    """Closes the database connection if it exists."""
    db_conn = g.pop('db', None)
    if db_conn is not None:
        db_conn.close()


def init_db():
    """Initializes the database and creates tables if they don't exist."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = ON")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cameras (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            camera_type TEXT NOT NULL,
            identifier TEXT NOT NULL UNIQUE
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pipelines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            pipeline_type TEXT NOT NULL DEFAULT 'AprilTag',
            camera_id INTEGER NOT NULL,
            config TEXT,
            FOREIGN KEY (camera_id) REFERENCES cameras (id) ON DELETE CASCADE
        );
    """)

    try:
        cursor.execute("ALTER TABLE cameras DROP COLUMN pipeline")
    except sqlite3.OperationalError:
        pass

    columns_to_add = {
        'orientation': 'INTEGER NOT NULL DEFAULT 0',
        'exposure_mode': 'TEXT NOT NULL DEFAULT "auto"',
        'exposure_value': 'INTEGER NOT NULL DEFAULT 500',
        'gain_mode': 'TEXT NOT NULL DEFAULT "auto"',
        'gain_value': 'INTEGER NOT NULL DEFAULT 50',
    }

    for column, definition in columns_to_add.items():
        try:
            cursor.execute(f"SELECT {column} FROM cameras LIMIT 1")
        except sqlite3.OperationalError:
            cursor.execute(f"ALTER TABLE cameras ADD COLUMN {column} {definition}")

    calibration_columns_to_add = {
        'camera_matrix_json': 'TEXT',
        'dist_coeffs_json': 'TEXT',
        'reprojection_error': 'REAL'
    }

    for column, definition in calibration_columns_to_add.items():
        try:
            cursor.execute(f"SELECT {column} FROM cameras LIMIT 1")
        except sqlite3.OperationalError:
            cursor.execute(f"ALTER TABLE cameras ADD COLUMN {column} {definition}")

    try:
        cursor.execute("SELECT config FROM pipelines LIMIT 1")
    except sqlite3.OperationalError:
        cursor.execute("ALTER TABLE pipelines ADD COLUMN config TEXT")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
    """)
    conn.commit()
    conn.close()


def add_camera(name, camera_type, identifier):
    """Adds a new camera to the database and returns its ID."""
    db = get_db()
    try:
        cursor = db.cursor()
        cursor.execute(
            "INSERT INTO cameras (name, camera_type, identifier) VALUES (?, ?, ?)",
            (name, camera_type, identifier),
        )
        camera_id = cursor.lastrowid
        if camera_id:
            add_pipeline(camera_id, 'default', 'AprilTag')
            db.commit()
            return camera_id
    except sqlite3.IntegrityError:
        print(f"Camera with identifier '{identifier}' already exists.")
        return None


def get_cameras():
    """Retrieves all cameras from the database."""
    db = get_db()
    return db.execute("SELECT * FROM cameras").fetchall()


def get_camera(camera_id):
    """Retrieves a single camera by its ID."""
    db = get_db()
    return db.execute("SELECT * FROM cameras WHERE id = ?", (camera_id,)).fetchone()


def get_camera_by_identifier(identifier):
    """Retrieves a single camera by its unique identifier."""
    db = get_db()
    return db.execute("SELECT * FROM cameras WHERE identifier = ?", (identifier,)).fetchone()


def update_camera(camera_id, name):
    """Updates a camera's name in the database."""
    db = get_db()
    db.execute("UPDATE cameras SET name = ? WHERE id = ?", (name, camera_id))
    db.commit()


def update_camera_calibration(camera_id, matrix, dist_coeffs, error):
    """Saves the camera calibration data to the database."""
    db = get_db()
    db.execute(
        """UPDATE cameras SET
            camera_matrix_json = ?,
            dist_coeffs_json = ?,
            reprojection_error = ?
        WHERE id = ?""",
        (matrix, dist_coeffs, error, camera_id)
    )
    db.commit()


def update_camera_controls(camera_id, orientation, exposure_mode, exposure_value, gain_mode, gain_value):
    """Updates a camera's control settings in the database."""
    db = get_db()
    db.execute(
        """UPDATE cameras SET
            orientation = ?,
            exposure_mode = ?,
            exposure_value = ?,
            gain_mode = ?,
            gain_value = ?
        WHERE id = ?""",
        (orientation, exposure_mode, exposure_value, gain_mode, gain_value, camera_id)
    )
    db.commit()


def clear_setting(key):
    """Deletes a setting from the database by its key."""
    db = get_db()
    db.execute("DELETE FROM settings WHERE key = ?", (key,))
    db.commit()
    

def delete_camera(camera_id):
    """Deletes a camera from the database by its ID."""
    db = get_db()
    db.execute("DELETE FROM cameras WHERE id = ?", (camera_id,))
    db.commit()


def add_pipeline(camera_id, name, pipeline_type, config=None):
    """Adds a new pipeline to the database for a specific camera."""
    if config is None:
        config = json.dumps({})
    db = get_db()
    db.execute(
        "INSERT INTO pipelines (camera_id, name, pipeline_type, config) VALUES (?, ?, ?, ?)",
        (camera_id, name, pipeline_type, config),
    )
    db.commit()


def get_pipelines(camera_id):
    """Retrieves all pipelines for a specific camera."""
    db = get_db()
    return db.execute("SELECT * FROM pipelines WHERE camera_id = ?", (camera_id,)).fetchall()


def get_pipeline(pipeline_id):
    """Retrieves a single pipeline by its ID."""
    db = get_db()
    return db.execute("SELECT * FROM pipelines WHERE id = ?", (pipeline_id,)).fetchone()


def update_pipeline(pipeline_id, name, pipeline_type):
    """Updates a pipeline's name and type in the database."""
    db = get_db()
    db.execute(
        "UPDATE pipelines SET name = ?, pipeline_type = ? WHERE id = ?",
        (name, pipeline_type, pipeline_id)
    )
    db.commit()


def update_pipeline_config(pipeline_id, config):
    """Updates a pipeline's config in the database."""
    db = get_db()
    db.execute(
        "UPDATE pipelines SET config = ? WHERE id = ?",
        (json.dumps(config), pipeline_id)
    )
    db.commit()


def delete_pipeline(pipeline_id):
    """Deletes a pipeline from the database by its ID."""
    db = get_db()
    db.execute("DELETE FROM pipelines WHERE id = ?", (pipeline_id,))
    db.commit()


def get_setting(key):
    """Retrieves a setting value by its key."""
    db = get_db()
    setting = db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return setting['value'] if setting else ""


def update_setting(key, value):
    """Updates or inserts a setting."""
    db = get_db()
    db.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
        (key, value)
    )
    db.commit()


def factory_reset():
    """Deletes all data from all tables."""
    db = get_db()
    cursor = db.cursor()
    cursor.execute("DELETE FROM cameras")
    cursor.execute("DELETE FROM pipelines")
    cursor.execute("DELETE FROM settings")
    db.commit()