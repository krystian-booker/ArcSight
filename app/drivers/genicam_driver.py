import threading
import os

try:
    import cv2  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - OpenCV may be absent in tests
    class _MissingCV2:
        def __getattr__(self, name):
            raise ModuleNotFoundError(
                "OpenCV (cv2) is required for GenICam functionality but is not installed."
            )

    cv2 = _MissingCV2()  # type: ignore
from .base_driver import BaseDriver

# Attempt to import Harvesters and GenICam API
try:
    from harvesters.core import Harvester
    from genicam import genapi
except ImportError:  # pragma: no cover
    Harvester = None
    genapi = None

# --- Module-level Globals for Harvester ---
# A single Harvester instance and a lock to manage it, shared by all GenICam drivers.
_harvester = None
_harvester_lock = threading.Lock()


def _get_harvester():
    """
    Lazily initialize and return the global Harvester instance.

    Returns:
        Harvester: The global Harvester instance, or None if library is not available.
    """
    global _harvester
    with _harvester_lock:
        if _harvester is None and Harvester:
            _harvester = Harvester()
        return _harvester


def _reset_harvester():
    """
    Reset the global Harvester instance, allowing reinitialization.

    This is useful when the CTI path changes or for cleanup.
    """
    global _harvester
    with _harvester_lock:
        if _harvester is not None:
            try:
                _harvester.reset()
            except Exception as e:
                print(f"Error resetting Harvester: {e}")
            finally:
                _harvester = None


# --- GenICam Constants ---
if genapi:
    SUPPORTED_INTERFACE_TYPES = {
        genapi.EInterfaceType.intfIInteger: "integer",
        genapi.EInterfaceType.intfIFloat: "float",
        genapi.EInterfaceType.intfIString: "string",
        genapi.EInterfaceType.intfIBoolean: "boolean",
        genapi.EInterfaceType.intfIEnumeration: "enumeration",
    }
    READABLE_ACCESS_MODES = {genapi.EAccessMode.RO, genapi.EAccessMode.RW}
    WRITABLE_ACCESS_MODES = {genapi.EAccessMode.WO, genapi.EAccessMode.RW}
else:
    SUPPORTED_INTERFACE_TYPES = {}
    READABLE_ACCESS_MODES = set()
    WRITABLE_ACCESS_MODES = set()


class GenICamDriver(BaseDriver):
    """
    Driver for GenICam compliant cameras using the Harvesters library.
    """

    def __init__(self, camera_db_data):
        super().__init__(camera_db_data)
        self.ia = None  # Image Acquirer instance

    def connect(self):
        h = _get_harvester()
        if not h:
            raise ConnectionError(
                "Harvesters library is not installed or failed to import."
            )

        with _harvester_lock:
            try:
                # The identifier for GenICam is the camera's serial number.
                self.ia = h.create({"serial_number": self.identifier})
                self.ia.start()
                print(f"Successfully connected to GenICam camera {self.identifier}")
            except Exception as e:
                # If creation fails, clean up and re-raise.
                if self.ia:
                    self.ia.destroy()
                    self.ia = None
                raise ConnectionError(
                    f"Failed to create ImageAcquirer for GenICam camera {self.identifier}: {e}"
                )

    def disconnect(self):
        if self.ia:
            print(f"Disconnecting GenICam camera {self.identifier}")
            try:
                self.ia.stop()
                self.ia.destroy()
            except Exception as e:
                print(f"Error during GenICam disconnect for {self.identifier}: {e}")
            finally:
                self.ia = None

    def get_frame(self):
        if not self.ia:
            return None

        try:
            # Use a timeout to prevent blocking indefinitely if the camera stops sending frames.
            with self.ia.fetch(timeout=2.0) as buffer:
                component = buffer.payload.components[0]
                img = component.data.reshape(component.height, component.width)

                # Convert frame to BGR format for consistency with OpenCV.
                if "Bayer" in component.data_format:
                    # Example for BayerRG; the specific conversion might need to be configurable.
                    return cv2.cvtColor(img, cv2.COLOR_BayerRG2BGR)
                elif len(img.shape) == 2:  # Grayscale image
                    return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
                else:
                    return img  # Assume it's already in a compatible format (e.g., BGR)
        except (genapi.TimeoutException, genapi.LogicalErrorException) as e:
            print(
                f"Frame acquisition timeout for GenICam {self.identifier}: {e}. Connection may be lost."
            )
            # Returning None signals the acquisition loop to attempt reconnection.
            return None
        except Exception as e:
            print(f"Unexpected error fetching GenICam frame for {self.identifier}: {e}")
            return None

    @staticmethod
    def initialize(cti_path=None):
        """
        Initializes the shared Harvester instance with a CTI file.
        This must be called once at application startup.

        Args:
            cti_path: Path to the CTI (Camera Transport Interface) file.

        Note:
            If the CTI path changes, call this method again to reinitialize
            with the new path. The previous Harvester instance will be reset.
        """
        if not Harvester:
            print("Cannot initialize GenICam driver: Harvesters library not installed.")
            return

        # Reset any existing harvester to allow reinitialization
        _reset_harvester()

        # Only create a Harvester instance if we have a valid CTI path
        if cti_path and os.path.exists(cti_path):
            # Get a fresh harvester instance
            h = _get_harvester()
            if not h:
                print("Failed to create Harvester instance.")
                return

            with _harvester_lock:
                try:
                    h.add_file(cti_path)
                    h.update()
                    print(f"Harvester initialized successfully with CTI: {cti_path}")
                except Exception as e:
                    print(f"Error initializing Harvester with CTI {cti_path}: {e}")
                    # Reset on failure to leave in clean state
                    _reset_harvester()
        else:
            print(
                "GenICam CTI file not found or not configured. Harvester is uninitialized."
            )
            # Don't create a Harvester instance if we don't have a CTI path
            # _harvester is already None from the _reset_harvester() call above

    @staticmethod
    def list_devices():
        """
        Returns a list of available GenICam devices found by the Harvester instance.
        """
        h = _get_harvester()
        if not h:
            return []

        devices = []
        with _harvester_lock:
            try:
                h.update()
                for device_info in h.device_info_list:
                    # The unique serial number is the ideal identifier.
                    if device_info.serial_number:
                        devices.append(
                            {
                                "identifier": device_info.serial_number,
                                "name": f"{device_info.model} ({device_info.serial_number})",
                                "camera_type": "GenICam",
                            }
                        )
            except Exception as e:
                print(f"Error listing GenICam cameras: {e}")
        return devices

    @staticmethod
    def _create_image_acquirer(identifier):
        """Creates and returns an image acquirer for a GenICam device."""
        h = _get_harvester()
        if not h or not identifier:
            return None, "Harvester not initialized or identifier missing."
        with _harvester_lock:
            try:
                # This creates a temporary connection to the camera to access the node map.
                # It does not interfere with the main acquisition connection.
                return h.create({"serial_number": identifier}), None
            except Exception as error:
                print(
                    f"Error creating temporary ImageAcquirer for {identifier}: {error}"
                )
                return None, f"Error creating ImageAcquirer for {identifier}: {error}"

    @staticmethod
    def get_node_map(identifier):
        """Retrieves the full node map for a specific GenICam device."""
        if not genapi:
            return [], "GenICam runtime (GenAPI) is not available on the server."

        ia, error = GenICamDriver._create_image_acquirer(identifier)
        if error:
            return [], error

        try:
            node_map = ia.remote_device.node_map
            nodes = []
            for node_wrapper in node_map.nodes:
                try:
                    interface_type = node_wrapper.node.principal_interface_type
                except Exception:
                    continue
                if interface_type not in SUPPORTED_INTERFACE_TYPES:
                    continue

                try:
                    access_value = node_wrapper.node.get_access_mode()
                    access_mode = genapi.EAccessMode(access_value)
                except (ValueError, TypeError):
                    access_mode = None

                is_readable = (
                    access_mode in READABLE_ACCESS_MODES if access_mode else False
                )
                is_writable = (
                    access_mode in WRITABLE_ACCESS_MODES if access_mode else False
                )
                node = node_wrapper.node
                display_name = str(getattr(node, "display_name", "") or "")
                name = str(getattr(node, "name", "") or "")
                description = str(
                    getattr(node, "tooltip", "")
                    or getattr(node, "description", "")
                    or ""
                )

                node_info = {
                    "name": name,
                    "display_name": display_name or name,
                    "description": description.strip(),
                    "interface_type": SUPPORTED_INTERFACE_TYPES[interface_type],
                    "access_mode": access_mode.name
                    if access_mode
                    else str(access_value),
                    "is_readable": is_readable,
                    "is_writable": is_writable,
                    "value": None,
                    "choices": [],
                }

                if is_readable:
                    try:
                        node_info["value"] = str(node_wrapper.to_string())
                    except Exception as read_error:
                        print(f"Error reading node {name}: {read_error}")
                if interface_type == genapi.EInterfaceType.intfIEnumeration:
                    try:
                        node_info["choices"] = [
                            str(symbol) for symbol in node_wrapper.symbolics
                        ]
                    except Exception as enum_error:
                        print(f"Error retrieving enum values for {name}: {enum_error}")
                nodes.append(node_info)
            nodes.sort(key=lambda item: item["display_name"].lower())
            return nodes, None
        except Exception as e:
            return [], f"Failed to retrieve node map: {e}"
        finally:
            if ia:
                ia.destroy()

    @staticmethod
    def update_node(identifier, node_name, value):
        """Updates a specific node on a GenICam device."""
        if not genapi:
            return False, "GenICam runtime is not available.", 500, None
        if not node_name:
            return False, "Node name is required.", 400, None

        ia, error = GenICamDriver._create_image_acquirer(identifier)
        if error:
            return False, f"Unable to connect to the GenICam camera: {error}", 500, None

        try:
            node = ia.remote_device.node_map.get_node(node_name)
            if node is None:
                return False, f"Node '{node_name}' not found.", 404, None

            access_mode = genapi.EAccessMode(node.get_access_mode())
            if access_mode not in WRITABLE_ACCESS_MODES:
                return False, f"Node '{node_name}' is not writable.", 400, None
            if value is None:
                return False, "A value must be provided.", 400, None

            try:
                if isinstance(node, genapi.IInteger):
                    node.set_value(int(value))
                elif isinstance(node, genapi.IFloat):
                    node.set_value(float(value))
                elif isinstance(node, genapi.IBoolean):
                    norm_val = str(value).strip().lower()
                    if norm_val in ("true", "1", "yes", "on"):
                        node.set_value(True)
                    elif norm_val in ("false", "0", "no", "off"):
                        node.set_value(False)
                    else:
                        return False, f"'{value}' is not a valid boolean.", 400, None
                else:
                    node.from_string(str(value))
            except Exception as set_error:
                return (
                    False,
                    f"Failed to update node '{node_name}': {set_error}",
                    400,
                    None,
                )

            # The node value is read back after setting it to confirm the change.
            # This requires re-establishing a connection in this stateless model.
            ia.destroy()
            ia = None

            # Re-acquire to read the value back.
            ia_read, error_read = GenICamDriver._create_image_acquirer(identifier)
            if error_read:
                return True, "Node updated, but failed to verify new state.", 200, None

            try:
                updated_node_wrapper = ia_read.remote_device.node_map.get_node(
                    node_name
                )
                updated_value = str(updated_node_wrapper.to_string())
                updated_node_info = {"name": node_name, "value": updated_value}
                return True, "Node updated successfully.", 200, updated_node_info
            finally:
                if ia_read:
                    ia_read.destroy()

        except Exception as e:
            return False, f"Unexpected error while updating node: {e}", 500, None
        finally:
            if ia:
                ia.destroy()
