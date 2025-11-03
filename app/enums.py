"""Enumeration types for type-safe constants throughout the application."""

from enum import Enum


class PipelineType(str, Enum):
    """Vision pipeline types supported by the application."""

    APRILTAG = "AprilTag"
    COLOURED_SHAPE = "Coloured Shape"
    OBJECT_DETECTION_ML = "Object Detection (ML)"

    @classmethod
    def from_string(cls, value: str) -> "PipelineType":
        """
        Convert a string to PipelineType enum.

        Args:
            value: String representation of pipeline type

        Returns:
            PipelineType enum value

        Raises:
            ValueError: If value doesn't match any known pipeline type
        """
        for pipeline_type in cls:
            if pipeline_type.value == value:
                return pipeline_type
        raise ValueError(f"Unknown pipeline type: {value}")

    def __str__(self) -> str:
        """Return the string value of the enum."""
        return self.value


class CameraType(str, Enum):
    """Camera driver types supported by the application."""

    USB = "USB"
    GENICAM = "GenICam"
    OAKD = "OAK-D"
    REALSENSE = "RealSense"

    @classmethod
    def from_string(cls, value: str) -> "CameraType":
        """
        Convert a string to CameraType enum.

        Args:
            value: String representation of camera type

        Returns:
            CameraType enum value

        Raises:
            ValueError: If value doesn't match any known camera type
        """
        for camera_type in cls:
            if camera_type.value == value:
                return camera_type
        raise ValueError(f"Unknown camera type: {value}")

    def __str__(self) -> str:
        """Return the string value of the enum."""
        return self.value


class ExposureMode(str, Enum):
    """Camera exposure control modes."""

    AUTO = "auto"
    MANUAL = "manual"

    def __str__(self) -> str:
        """Return the string value of the enum."""
        return self.value


class GainMode(str, Enum):
    """Camera gain control modes."""

    AUTO = "auto"
    MANUAL = "manual"

    def __str__(self) -> str:
        """Return the string value of the enum."""
        return self.value


class Orientation(int, Enum):
    """Camera orientation angles in degrees."""

    NORMAL = 0
    ROTATE_90 = 90
    ROTATE_180 = 180
    ROTATE_270 = 270

    @classmethod
    def from_degrees(cls, degrees: int) -> "Orientation":
        """
        Convert degrees to Orientation enum.

        Args:
            degrees: Rotation angle in degrees

        Returns:
            Orientation enum value

        Raises:
            ValueError: If degrees is not a valid orientation
        """
        # Normalize to 0-360 range
        normalized = degrees % 360
        for orientation in cls:
            if orientation.value == normalized:
                return orientation
        raise ValueError(f"Invalid orientation angle: {degrees}")


class AprilTagFamily(str, Enum):
    """AprilTag family types."""

    TAG36H11 = "tag36h11"
    TAG25H9 = "tag25h9"
    TAG16H5 = "tag16h5"
    TAGCIRCLE21H7 = "tagCircle21h7"
    TAGCIRCLE49H12 = "tagCircle49h12"
    TAGSTANDARD41H12 = "tagStandard41h12"
    TAGSTANDARD52H13 = "tagStandard52h13"
    TAGCUSTOM48H12 = "tagCustom48h12"

    def __str__(self) -> str:
        """Return the string value of the enum."""
        return self.value


