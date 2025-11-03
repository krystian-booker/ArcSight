"""
Camera type registry for dynamic camera driver management.

This module provides a centralized registry of available camera types,
allowing the frontend to discover available drivers without hardcoded logic.
"""

from typing import List, Dict, Any
from app.enums import CameraType


# Camera type registry with metadata for frontend display
CAMERA_TYPE_REGISTRY = [
    {
        "type": CameraType.USB.value,
        "name": "USB Camera",
        "description": "Standard USB webcams and capture devices",
        "requires_library": False,
        "discovery_supported": True,
    },
    {
        "type": CameraType.GENICAM.value,
        "name": "GenICam Camera",
        "description": "Industrial cameras supporting GenICam standard (requires Harvesters)",
        "requires_library": True,
        "library_name": "harvesters-core",
        "discovery_supported": True,
    },
    {
        "type": CameraType.OAKD.value,
        "name": "OAK-D Camera",
        "description": "Luxonis OAK-D depth cameras (requires DepthAI)",
        "requires_library": True,
        "library_name": "depthai",
        "discovery_supported": True,
    },
    {
        "type": CameraType.REALSENSE.value,
        "name": "Intel RealSense",
        "description": "Intel RealSense depth cameras (requires pyrealsense2)",
        "requires_library": True,
        "library_name": "pyrealsense2",
        "discovery_supported": True,
    },
]


def get_camera_types() -> List[Dict[str, Any]]:
    """
    Get list of all registered camera types with metadata.

    Returns:
        List of camera type dictionaries with metadata for frontend display
    """
    return CAMERA_TYPE_REGISTRY.copy()


def get_camera_type_info(camera_type: str) -> Dict[str, Any]:
    """
    Get metadata for a specific camera type.

    Args:
        camera_type: Camera type identifier (e.g., 'USB', 'GenICam')

    Returns:
        Dictionary with camera type metadata, or empty dict if not found
    """
    for type_info in CAMERA_TYPE_REGISTRY:
        if type_info["type"] == camera_type:
            return type_info.copy()
    return {}


def is_valid_camera_type(camera_type: str) -> bool:
    """
    Check if a camera type is valid and registered.

    Args:
        camera_type: Camera type identifier to validate

    Returns:
        True if camera type is registered, False otherwise
    """
    return any(t["type"] == camera_type for t in CAMERA_TYPE_REGISTRY)
