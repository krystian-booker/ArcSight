import platform
import socket
import subprocess
import psutil


def get_hostname():
    """Retrieves the hostname of the local machine."""
    return socket.gethostname()


def get_network_settings():
    """Retrieves network settings, indicating whether the primary interface is using DHCP or a static IP."""
    os_type = platform.system()
    if os_type == "Windows":
        return get_windows_network_settings()
    elif os_type == "Linux":
        return get_linux_network_settings()
    elif os_type == "Darwin":
        return get_macos_network_settings()
    else:
        return {"ip_mode": "Unknown", "hostname": get_hostname()}


def get_primary_interface_name():
    """Identifies the name of the primary network interface."""
    try:
        stats = psutil.net_if_stats()
        connections = psutil.net_connections(kind="inet")

        for conn in connections:
            if conn.status == "ESTABLISHED" and conn.raddr:
                laddr_ip = conn.laddr.ip
                for intface, addrs in psutil.net_if_addrs().items():
                    for addr in addrs:
                        if addr.address == laddr_ip:
                            return intface

        for intface, stat in stats.items():
            if stat.isup and "lo" not in intface.lower():
                return intface

    except Exception:
        return None
    return None


def get_windows_network_settings():
    """Retrieves network settings on Windows by parsing 'ipconfig' output."""
    try:
        primary_interface = get_primary_interface_name()
        if not primary_interface:
            return {"ip_mode": "Unknown"}

        output = subprocess.check_output(["ipconfig", "/all"], text=True)
        interface_section = None
        for line in output.splitlines():
            if "Ethernet adapter" in line or "Wireless LAN adapter" in line:
                if primary_interface in line:
                    interface_section = ""
                else:
                    interface_section = None
            if interface_section is not None:
                interface_section += line + "\n"

        if interface_section:
            for line in interface_section.splitlines():
                if "DHCP Enabled" in line and "Yes" in line:
                    return {"ip_mode": "DHCP"}
        return {"ip_mode": "Static"}
    except (subprocess.CalledProcessError, FileNotFoundError):
        return {"ip_mode": "Unknown"}


def get_linux_network_settings():
    """Retrieves network settings on Linux using 'nmcli'."""
    try:
        primary_interface = get_primary_interface_name()
        if not primary_interface:
            return {"ip_mode": "Unknown"}

        output = subprocess.check_output(
            ["nmcli", "-t", "-f", "DEVICE,NAME", "con", "show", "--active"], text=True
        )
        connection_name = None
        for line in output.splitlines():
            if line.startswith(primary_interface + ":"):
                connection_name = line.split(":")[1]
                break

        if not connection_name:
            return {"ip_mode": "Unknown"}

        output = subprocess.check_output(
            ["nmcli", "-t", "-f", "ipv4.method", "con", "show", connection_name],
            text=True,
        )
        if "auto" in output:
            return {"ip_mode": "DHCP"}
        else:
            return {"ip_mode": "Static"}
    except (subprocess.CalledProcessError, FileNotFoundError):
        return {"ip_mode": "Unknown"}


def get_macos_network_settings():
    """Retrieves network settings on macOS using 'networksetup'."""
    try:
        primary_interface = get_primary_interface_name()
        if not primary_interface:
            output = subprocess.check_output(
                ["networksetup", "-listallnetworkservices"], text=True
            )
            services = output.splitlines()[1:]
            for service in services:
                if "wi-fi" in service.lower() or "ethernet" in service.lower():
                    primary_interface = service
                    break
            if not primary_interface:
                return {"ip_mode": "Unknown"}

        output = subprocess.check_output(
            ["networksetup", "-getinfo", primary_interface], text=True
        )
        if "DHCP" in output:
            return {"ip_mode": "DHCP"}
        else:
            return {"ip_mode": "Static"}
    except (subprocess.CalledProcessError, FileNotFoundError):
        return {"ip_mode": "Unknown"}
