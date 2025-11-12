from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from appdirs import user_data_dir

from app.extensions import db
from app.models import Setting

APP_NAME = "VisionTools"
APP_AUTHOR = "User"
_DEFAULT_FIELDS_DIR = Path(__file__).resolve().parent.parent / "data"
_USER_FIELDS_SUBDIR = "apriltag_fields"
MAX_FIELD_FILE_SIZE = 1 * 1024 * 1024  # 1 MiB hard limit for uploads


@dataclass(frozen=True)
class FieldInfo:
    """Simple descriptor for an AprilTag field layout."""

    name: str
    path: str
    source: str  # "default" or "user"

    @property
    def is_default(self) -> bool:
        return self.source == "default"


def ensure_user_fields_dir() -> str:
    """Ensures the user-specific AprilTag field directory exists and returns its path."""
    base_dir = user_data_dir(APP_NAME, APP_AUTHOR)
    fields_dir = os.path.join(base_dir, _USER_FIELDS_SUBDIR)
    os.makedirs(fields_dir, exist_ok=True)
    return fields_dir


def _scan_directory(directory: Path, source: str) -> List[FieldInfo]:
    if not directory.exists() or not directory.is_dir():
        return []

    infos: List[FieldInfo] = []
    for entry in sorted(directory.iterdir()):
        if entry.is_file() and entry.suffix.lower() == ".json":
            infos.append(FieldInfo(name=entry.name, path=str(entry), source=source))
    return infos


def get_default_fields() -> List[FieldInfo]:
    """Returns available built-in field layouts."""
    return _scan_directory(_DEFAULT_FIELDS_DIR, "default")


def get_user_fields() -> List[FieldInfo]:
    """Returns AprilTag field layouts uploaded by the user."""
    return _scan_directory(Path(ensure_user_fields_dir()), "user")


def _sort_key(field: FieldInfo) -> Tuple[int, str]:
    """Sort by leading year (if present) descending, otherwise by name."""
    digits = []
    for char in field.name:
        if char.isdigit():
            digits.append(char)
        else:
            break
    year = 0
    if len(digits) >= 4:
        try:
            year = int("".join(digits[:4]))
        except ValueError:
            year = 0
    return (-year, field.name.lower())


def list_all_fields() -> List[FieldInfo]:
    """Merges default and user fields, preferring user overrides when names clash."""
    combined: Dict[str, FieldInfo] = {}
    for info in get_default_fields():
        combined.setdefault(info.name, info)

    for info in get_user_fields():
        combined[info.name] = info

    return sorted(combined.values(), key=_sort_key)


def get_selected_field_name() -> Optional[str]:
    """Return the persisted field selection, if any."""
    try:
        setting = db.session.get(Setting, "apriltag_field")
    except RuntimeError:
        # Outside of an application context the lookup is not available.
        return None
    if setting and setting.value:
        return setting.value
    return None


def _validate_quaternion_keys(quaternion: Dict) -> bool:
    required = {"W", "X", "Y", "Z"}
    lower_required = {"w", "x", "y", "z"}
    if required.issubset(quaternion.keys()):
        return True
    if lower_required.issubset(quaternion.keys()):
        return True
    return False


def validate_layout_structure(data: Dict) -> Tuple[bool, Optional[str]]:
    """Perform minimal structural validation for an AprilTag field layout."""
    if not isinstance(data, dict):
        return False, "Layout JSON must be an object"

    tags = data.get("tags")
    if not isinstance(tags, list):
        return False, "Layout must define a 'tags' array"

    for index, tag in enumerate(tags):
        if not isinstance(tag, dict):
            return False, f"Tag entry at index {index} must be an object"
        if "ID" not in tag:
            return False, f"Tag entry at index {index} is missing 'ID'"
        pose = tag.get("pose")
        if not isinstance(pose, dict):
            return False, f"Tag {tag.get('ID', index)} is missing 'pose'"

        translation = pose.get("translation")
        if not isinstance(translation, dict):
            return False, f"Tag {tag.get('ID', index)} pose missing 'translation'"
        for axis in ("x", "y", "z"):
            if axis not in translation:
                return (
                    False,
                    f"Tag {tag.get('ID', index)} translation missing '{axis}'",
                )

        rotation = pose.get("rotation")
        if not isinstance(rotation, dict):
            return False, f"Tag {tag.get('ID', index)} pose missing 'rotation'"

        quaternion = rotation.get("quaternion")
        if not isinstance(quaternion, dict):
            return False, f"Tag {tag.get('ID', index)} rotation missing 'quaternion'"
        if not _validate_quaternion_keys(quaternion):
            return (
                False,
                f"Tag {tag.get('ID', index)} quaternion missing components W/X/Y/Z",
            )

    return True, None


def _load_layout(path: str) -> Optional[Dict]:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None

    is_valid, error = validate_layout_structure(data)
    if not is_valid:
        print(f"Rejected AprilTag field layout '{path}': {error}")
        return None
    return data


def load_field_layout_by_name(name: str) -> Optional[Dict]:
    """Locate, validate, and return the JSON dict for a named layout."""
    if not name:
        return None

    fields = {info.name: info for info in list_all_fields()}
    info = fields.get(name)
    if not info:
        return None

    return _load_layout(info.path)


def get_all_field_names_by_source() -> Dict[str, List[str]]:
    """Helper for templates/tests to obtain names grouped by source."""
    grouped: Dict[str, List[str]] = {"default": [], "user": []}
    for info in list_all_fields():
        grouped.setdefault(info.source, []).append(info.name)
    return grouped
