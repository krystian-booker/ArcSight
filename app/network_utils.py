import platform
import socket
import subprocess
import psutil

def get_hostname():
    """
    Retrieves the hostname of the local machine.
    This function is cross-platform and should work on Windows, Linux, and macOS.
    """
    return socket.gethostname()

def get_network_settings():
    """
    Retrieves network settings, focusing on whether the primary interface is set to DHCP or Static.
    This function is designed to be cross-platform.
    """
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
    """
    Identifies the primary network interface name.
    This is a helper function that attempts to find the interface most likely
    to be the primary one for internet connectivity.
    """
    try:
        # Get all network interfaces and their stats
        stats = psutil.net_if_stats()
        # Get all network connections
        connections = psutil.net_connections(kind='inet')
        
        # Find the interface associated with the default route
        for conn in connections:
            if conn.status == 'ESTABLISHED' and conn.raddr:
                # This logic assumes the default route is used for established connections
                # It's not foolproof but a good heuristic
                laddr_ip = conn.laddr.ip
                # Find the interface with this local IP
                for intface, addrs in psutil.net_if_addrs().items():
                    for addr in addrs:
                        if addr.address == laddr_ip:
                            return intface
        
        # Fallback: find the first 'up' and non-loopback interface
        for intface, stat in stats.items():
            if stat.isup and 'lo' not in intface.lower():
                return intface
                
    except Exception:
        return None
    return None

def get_windows_network_settings():
    """
    On Windows, parse the output of `ipconfig /all` to find if DHCP is enabled
    for the primary network interface.
    """
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
    """
    On Linux, use `nmcli` to determine the IP assignment mode.
    This is a common tool on modern Linux distributions.
    """
    try:
        primary_interface = get_primary_interface_name()
        if not primary_interface:
            return {"ip_mode": "Unknown"}
            
        # Get the connection name for the primary interface
        output = subprocess.check_output(["nmcli", "-t", "-f", "DEVICE,NAME", "con", "show", "--active"], text=True)
        connection_name = None
        for line in output.splitlines():
            if line.startswith(primary_interface + ":"):
                connection_name = line.split(':')[1]
                break
        
        if not connection_name:
            return {"ip_mode": "Unknown"}

        # Check the IP assignment method for that connection
        output = subprocess.check_output(["nmcli", "-t", "-f", "ipv4.method", "con", "show", connection_name], text=True)
        if "auto" in output:
            return {"ip_mode": "DHCP"}
        else:
            return {"ip_mode": "Static"}
    except (subprocess.CalledProcessError, FileNotFoundError):
        # Fallback for systems without nmcli
        return {"ip_mode": "Unknown"}

def get_macos_network_settings():
    """
    On macOS, use the `networksetup` command to check for DHCP.
    """
    try:
        primary_interface = get_primary_interface_name()
        if not primary_interface:
            # On macOS, interfaces often have user-friendly names like "Wi-Fi" or "Ethernet"
            # Let's try to get the service name associated with the interface device
            output = subprocess.check_output(["networksetup", "-listallnetworkservices"], text=True)
            services = output.splitlines()[1:] # Skip the header line
            for service in services:
                # Heuristic: Wi-Fi is common, otherwise check for Ethernet
                if "wi-fi" in service.lower() or "ethernet" in service.lower():
                    primary_interface = service
                    break
            if not primary_interface:
                return {"ip_mode": "Unknown"}

        output = subprocess.check_output(["networksetup", "-getinfo", primary_interface], text=True)
        if "DHCP" in output:
            return {"ip_mode": "DHCP"}
        else:
            return {"ip_mode": "Static"}
    except (subprocess.CalledProcessError, FileNotFoundError):
        return {"ip_mode": "Unknown"}