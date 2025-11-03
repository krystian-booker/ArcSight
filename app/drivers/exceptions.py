"""Custom exception hierarchy for camera drivers."""


class DriverError(Exception):
    """Base exception for all driver-related errors."""
    pass


class DriverConnectionError(DriverError):
    """Raised when a driver fails to connect to a camera."""
    pass


class DriverDisconnectionError(DriverError):
    """Raised when a driver fails to disconnect cleanly."""
    pass


class DriverFrameAcquisitionError(DriverError):
    """Raised when a driver fails to acquire a frame from the camera."""
    pass


class DriverConfigurationError(DriverError):
    """Raised when a driver configuration is invalid or fails to apply."""
    pass


class DriverNotAvailableError(DriverError):
    """Raised when required driver dependencies are not installed."""
    pass


class DriverDiscoveryError(DriverError):
    """Raised when device discovery fails."""
    pass


class DriverNodeError(DriverError):
    """Raised when GenICam node operations fail."""
    pass
