"""Vite development server manager.

Manages the lifecycle of the Vite dev server when running Flask in development mode.
"""

import subprocess
import time
import requests
import os
import signal
import atexit
from typing import Optional
import sys


class ViteManager:
    """Manages Vite dev server lifecycle."""

    def __init__(self, vite_url: str = "http://localhost:5173", frontend_dir: str = "frontend"):
        """Initialize ViteManager.

        Args:
            vite_url: URL where Vite dev server will run
            frontend_dir: Directory containing Vite project (relative to project root)
        """
        self.vite_url = vite_url
        self.frontend_dir = frontend_dir
        self.process: Optional[subprocess.Popen] = None
        self._is_running = False

    def start(self, timeout: int = 30) -> bool:
        """Start Vite dev server.

        Args:
            timeout: Maximum seconds to wait for server to be ready

        Returns:
            True if server started successfully, False otherwise
        """
        # Check if already running
        if self._check_server_health():
            print(f"Vite dev server already running at {self.vite_url}")
            self._is_running = True
            return True

        # Get project root (parent of app directory)
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        frontend_path = os.path.join(project_root, self.frontend_dir)

        if not os.path.exists(frontend_path):
            print(f"ERROR: Frontend directory not found: {frontend_path}")
            return False

        # Check if package.json exists
        package_json = os.path.join(frontend_path, "package.json")
        if not os.path.exists(package_json):
            print(f"ERROR: package.json not found in {frontend_path}")
            return False

        print(f"\nStarting Vite dev server from {frontend_path}...")

        try:
            # Start Vite process
            # Use 'npm.cmd' on Windows, 'npm' on Unix
            npm_cmd = 'npm.cmd' if sys.platform == 'win32' else 'npm'

            self.process = subprocess.Popen(
                [npm_cmd, 'run', 'dev'],
                cwd=frontend_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
                # On Windows, create new process group to allow clean shutdown
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == 'win32' else 0,
                # On Unix, create new session to allow clean shutdown
                preexec_fn=os.setsid if sys.platform != 'win32' else None,
            )

            # Register cleanup handler
            atexit.register(self.stop)

            # Wait for server to be ready
            print(f"Waiting for Vite dev server at {self.vite_url}...")
            start_time = time.time()

            while time.time() - start_time < timeout:
                if self._check_server_health():
                    self._is_running = True
                    print(f"✓ Vite dev server is ready at {self.vite_url}")
                    return True

                # Check if process died
                if self.process.poll() is not None:
                    stdout, stderr = self.process.communicate()
                    print(f"ERROR: Vite process exited unexpectedly")
                    if stdout:
                        print(f"STDOUT: {stdout.decode()}")
                    if stderr:
                        print(f"STDERR: {stderr.decode()}")
                    return False

                time.sleep(0.5)

            print(f"ERROR: Vite dev server failed to start within {timeout} seconds")
            self.stop()
            return False

        except Exception as e:
            print(f"ERROR: Failed to start Vite dev server: {e}")
            self.stop()
            return False

    def stop(self):
        """Stop Vite dev server."""
        if self.process is None:
            return

        print("\nStopping Vite dev server...")

        try:
            if sys.platform == 'win32':
                # On Windows, send CTRL_BREAK_EVENT to process group
                self.process.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                # On Unix, terminate the process group
                os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)

            # Wait for process to terminate
            try:
                self.process.wait(timeout=5)
                print("✓ Vite dev server stopped")
            except subprocess.TimeoutExpired:
                # Force kill if graceful shutdown failed
                print("Force killing Vite dev server...")
                self.process.kill()
                self.process.wait()
                print("✓ Vite dev server killed")

        except Exception as e:
            print(f"WARNING: Error stopping Vite dev server: {e}")
        finally:
            self.process = None
            self._is_running = False

    def _check_server_health(self) -> bool:
        """Check if Vite dev server is responding.

        Returns:
            True if server is healthy, False otherwise
        """
        try:
            response = requests.get(self.vite_url, timeout=1)
            return response.status_code == 200
        except Exception:
            return False

    def is_running(self) -> bool:
        """Check if Vite dev server is running.

        Returns:
            True if running, False otherwise
        """
        return self._is_running and self._check_server_health()


# Global instance
_vite_manager: Optional[ViteManager] = None


def get_vite_manager(vite_url: str = "http://localhost:5173") -> ViteManager:
    """Get global ViteManager instance.

    Args:
        vite_url: URL where Vite dev server will run

    Returns:
        ViteManager instance
    """
    global _vite_manager
    if _vite_manager is None:
        _vite_manager = ViteManager(vite_url=vite_url)
    return _vite_manager
