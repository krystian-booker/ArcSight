"""Settings business logic service layer."""

import logging
from typing import Optional, Dict, Any

from app.extensions import db
from app.models import Setting

logger = logging.getLogger(__name__)


class SettingsService:
    """Service class for application settings management."""

    @staticmethod
    def get_setting(key: str, default: Any = None) -> Any:
        """
        Get a setting value by key.

        Args:
            key: Setting key
            default: Default value if setting doesn't exist

        Returns:
            Setting value or default
        """
        setting = db.session.get(Setting, key)
        if setting:
            return setting.value if setting.value is not None else default
        return default

    @staticmethod
    def get_all_settings() -> Dict[str, Any]:
        """
        Get all settings as a dictionary.

        Returns:
            Dictionary of all settings (key: value)
        """
        settings = Setting.query.all()
        return {s.key: s.value for s in settings}

    @staticmethod
    def get_multiple_settings(keys: list, defaults: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Get multiple settings at once.

        Args:
            keys: List of setting keys to retrieve
            defaults: Optional dictionary of default values

        Returns:
            Dictionary of setting key-value pairs
        """
        if defaults is None:
            defaults = {}

        result = {}
        for key in keys:
            result[key] = SettingsService.get_setting(key, defaults.get(key, ""))
        return result

    @staticmethod
    def set_setting(key: str, value: Any) -> bool:
        """
        Set a setting value. Creates the setting if it doesn't exist.

        Args:
            key: Setting key
            value: Setting value

        Returns:
            True if successful, False otherwise
        """
        try:
            setting = db.session.get(Setting, key)
            if setting:
                setting.value = value
            else:
                setting = Setting(key=key, value=value)
                db.session.add(setting)

            db.session.commit()
            logger.info(f"Updated setting: {key}")
            return True

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error setting {key}: {e}")
            return False

    @staticmethod
    def set_multiple_settings(settings: Dict[str, Any]) -> bool:
        """
        Set multiple settings at once.

        Args:
            settings: Dictionary of key-value pairs to set

        Returns:
            True if all successful, False otherwise
        """
        try:
            for key, value in settings.items():
                setting = db.session.get(Setting, key)
                if setting:
                    setting.value = value
                else:
                    setting = Setting(key=key, value=value)
                    db.session.add(setting)

            db.session.commit()
            logger.info(f"Updated {len(settings)} settings")
            return True

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error setting multiple settings: {e}")
            return False

    @staticmethod
    def delete_setting(key: str) -> bool:
        """
        Delete a setting.

        Args:
            key: Setting key to delete

        Returns:
            True if successful, False otherwise
        """
        try:
            setting = db.session.get(Setting, key)
            if setting:
                db.session.delete(setting)
                db.session.commit()
                logger.info(f"Deleted setting: {key}")
                return True
            return False

        except Exception as e:
            db.session.rollback()
            logger.error(f"Error deleting setting {key}: {e}")
            return False

    @staticmethod
    def setting_exists(key: str) -> bool:
        """
        Check if a setting exists.

        Args:
            key: Setting key

        Returns:
            True if setting exists, False otherwise
        """
        return db.session.get(Setting, key) is not None

    # Convenience methods for common settings

    @staticmethod
    def get_genicam_cti_path() -> Optional[str]:
        """Get the GenICam CTI file path."""
        return SettingsService.get_setting("genicam_cti_path")

    @staticmethod
    def set_genicam_cti_path(path: str) -> bool:
        """Set the GenICam CTI file path."""
        return SettingsService.set_setting("genicam_cti_path", path)

    @staticmethod
    def get_team_number() -> str:
        """Get the FRC team number."""
        return SettingsService.get_setting("team_number", "")

    @staticmethod
    def set_team_number(team_number: str) -> bool:
        """Set the FRC team number."""
        return SettingsService.set_setting("team_number", team_number)

    @staticmethod
    def get_ip_mode() -> str:
        """Get the IP configuration mode (dhcp or static)."""
        return SettingsService.get_setting("ip_mode", "dhcp")

    @staticmethod
    def set_ip_mode(mode: str) -> bool:
        """Set the IP configuration mode."""
        return SettingsService.set_setting("ip_mode", mode)

    @staticmethod
    def get_hostname() -> str:
        """Get the configured hostname."""
        return SettingsService.get_setting("hostname", "")

    @staticmethod
    def set_hostname(hostname: str) -> bool:
        """Set the hostname."""
        return SettingsService.set_setting("hostname", hostname)

    @staticmethod
    def get_apriltag_field() -> Optional[str]:
        """Get the selected AprilTag field layout."""
        return SettingsService.get_setting("apriltag_field")

    @staticmethod
    def set_apriltag_field(field_name: str) -> bool:
        """Set the selected AprilTag field layout."""
        return SettingsService.set_setting("apriltag_field", field_name)
