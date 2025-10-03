from .drivers.usb_driver import USBDriver
from .drivers.genicam_driver import GenICamDriver
from .drivers.oakd_driver import OAKDDriver


# --- Driver Factory ---
def get_driver(camera_db_data):
    """Factory function to get the correct driver instance."""
    camera_type = camera_db_data['camera_type']
    if camera_type == 'USB':
        return USBDriver(camera_db_data)
    elif camera_type == 'GenICam':
        return GenICamDriver(camera_db_data)
    elif camera_type == 'OAK-D':
        return OAKDDriver(camera_db_data)
    else:
        raise ValueError(f"Unknown camera type: {camera_type}")


# --- Camera Discovery ---
def discover_cameras(existing_identifiers):
    """Discovers all available cameras by polling the drivers."""
    print("Discovering cameras...")
    usb_cams = [c for c in USBDriver.list_devices() if c['identifier'] not in existing_identifiers]
    genicam_cams = [c for c in GenICamDriver.list_devices() if c['identifier'] not in existing_identifiers]
    oakd_cams = [c for c in OAKDDriver.list_devices() if c['identifier'] not in existing_identifiers]
    
    print(f"Found {len(usb_cams)} new USB, {len(genicam_cams)} new GenICam, {len(oakd_cams)} new OAK-D cameras.")
    return {'usb': usb_cams, 'genicam': genicam_cams, 'oakd': oakd_cams}