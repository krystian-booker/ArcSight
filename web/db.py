import sqlite3
import os
from appdirs import user_data_dir

# Define the application name and author for appdirs
APP_NAME = "VisionTools"
APP_AUTHOR = "User"

# Get the user data directory
data_dir = user_data_dir(APP_NAME, APP_AUTHOR)

# Create the directory if it doesn't exist
os.makedirs(data_dir, exist_ok=True)

# Define the database path
DB_PATH = os.path.join(data_dir, "config.db")

def get_db_connection():
    """Establishes a connection to the database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initializes the database and creates tables if they don't exist."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cameras (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            camera_type TEXT NOT NULL,
            identifier TEXT NOT NULL UNIQUE,
            pipeline TEXT NOT NULL DEFAULT 'AprilTag'
        );
    """)
    
    # Migration: Add pipeline column if it doesn't exist
    try:
        cursor.execute("SELECT pipeline FROM cameras LIMIT 1")
    except sqlite3.OperationalError:
        cursor.execute("ALTER TABLE cameras ADD COLUMN pipeline TEXT NOT NULL DEFAULT 'AprilTag'")

    # Migration: Add camera control columns if they don't exist
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

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
    """)
    conn.commit()
    conn.close()

def add_camera(name, camera_type, identifier):
    """Adds a new camera to the database."""
    conn = get_db_connection()
    try:
        conn.execute(
            "INSERT INTO cameras (name, camera_type, identifier, pipeline) VALUES (?, ?, ?, ?)",
            (name, camera_type, identifier, 'AprilTag'),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        print(f"Camera with identifier '{identifier}' already exists.")
        # In a real app, you might want to raise this exception
        # for the caller to handle, but for now we'll just ignore it.
    finally:
        conn.close()

def get_cameras():
    """Retrieves all cameras from the database."""
    conn = get_db_connection()
    cameras = conn.execute("SELECT * FROM cameras").fetchall()
    conn.close()
    return cameras

def get_camera(camera_id):
    """Retrieves a single camera by its ID."""
    conn = get_db_connection()
    camera = conn.execute("SELECT * FROM cameras WHERE id = ?", (camera_id,)).fetchone()
    conn.close()
    return camera

def update_camera(camera_id, name):
    """Updates a camera's name in the database."""
    conn = get_db_connection()
    conn.execute(
        "UPDATE cameras SET name = ? WHERE id = ?",
        (name, camera_id)
    )
    conn.commit()
    conn.close()

def update_camera_controls(camera_id, orientation, exposure_mode, exposure_value, gain_mode, gain_value):
    """Updates a camera's control settings in the database."""
    conn = get_db_connection()
    conn.execute(
        """UPDATE cameras SET
            orientation = ?,
            exposure_mode = ?,
            exposure_value = ?,
            gain_mode = ?,
            gain_value = ?
        WHERE id = ?""",
        (orientation, exposure_mode, exposure_value, gain_mode, gain_value, camera_id)
    )
    conn.commit()
    conn.close()

def update_camera_pipeline(camera_id, pipeline):
    """Updates a camera's pipeline in the database."""
    conn = get_db_connection()
    conn.execute(
        "UPDATE cameras SET pipeline = ? WHERE id = ?",
        (pipeline, camera_id)
    )
    conn.commit()
    conn.close()

def clear_setting(key):
    """Deletes a setting from the database by its key."""
    conn = get_db_connection()
    conn.execute("DELETE FROM settings WHERE key = ?", (key,))
    conn.commit()
    conn.close()
    
def delete_camera(camera_id):
    """Deletes a camera from the database by its ID."""
    conn = get_db_connection()
    conn.execute("DELETE FROM cameras WHERE id = ?", (camera_id,))
    conn.commit()
    conn.close()

def get_setting(key):
    """Retrieves a setting value by its key."""
    conn = get_db_connection()
    setting = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    conn.close()
    return setting['value'] if setting else ""

def update_setting(key, value):
    """Updates or inserts a setting."""
    conn = get_db_connection()
    conn.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
        (key, value)
    )
    conn.commit()
    conn.close()

def factory_reset():
    """Deletes all data from all tables."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM cameras")
    cursor.execute("DELETE FROM settings")
    conn.commit()
    conn.close()

# Initialize the database when this module is first imported.
init_db()
