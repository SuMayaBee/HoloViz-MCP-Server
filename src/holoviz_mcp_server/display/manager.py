"""Panel server subprocess management.

Manages the Panel server as a subprocess, including startup,
health checks, stale process recovery, and shutdown.
"""

import logging
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import psutil
import requests

from holoviz_mcp_server.platform import prepend_env_dll_paths

logger = logging.getLogger(__name__)


def _force_kill_pid(pid: int) -> bool:
    """Force-kill a process by PID using psutil (cross-platform)."""
    try:
        psutil.Process(pid).kill()
    except psutil.NoSuchProcess:
        pass
    except psutil.AccessDenied:
        logger.error(f"No permission to force-kill process (PID {pid})")
        return False
    return True


class PanelServerManager:
    """Manages the Panel server subprocess."""

    def __init__(
        self,
        db_path: Path,
        port: int = 5077,
        host: str = "localhost",
        max_restarts: int = 3,
    ):
        self.db_path = db_path
        self.port = port
        self.host = host
        self.max_restarts = max_restarts
        self.process: subprocess.Popen | None = None
        self.restart_count = 0

    def _build_subprocess_env(self) -> dict[str, str]:
        env = os.environ.copy()
        env["HOLOVIZ_MCP_SERVER_DB_PATH"] = str(self.db_path)
        env["HOLOVIZ_MCP_SERVER_PORT"] = str(self.port)
        env["HOLOVIZ_MCP_SERVER_HOST"] = self.host
        prepend_env_dll_paths(env)
        return env

    def _log_startup_failure(self) -> None:
        if self.process is None or self.process.poll() is None:
            return

        returncode = self.process.returncode
        try:
            stdout, stderr = self.process.communicate(timeout=1)
        except subprocess.TimeoutExpired:
            return

        logger.error(f"Panel server exited during startup with code {returncode}")
        if stdout and stdout.strip():
            logger.error(f"stdout:\n{stdout}")
        if stderr and stderr.strip():
            logger.error(f"stderr:\n{stderr}")

    def _is_port_in_use(self) -> bool:
        import socket

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((self.host, self.port))
                return False
            except OSError:
                return True

    def _try_recover_stale_server(self) -> bool:
        """Try to recover from a stale server occupying the port.

        Returns True if the port is now usable (either adopted a healthy server
        or successfully freed the port), False if we failed to clear the port.
        """
        # If a healthy server is already on the port, adopt it — no need to restart.
        try:
            response = requests.get(f"http://{self.host}:{self.port}/api/health", timeout=3)
            if response.status_code == 200:
                logger.info(f"Found healthy Panel server already running on port {self.port} — adopting it")
                return True
        except requests.RequestException:
            pass

        # Server is unresponsive — try to clear the port.
        logger.warning(f"Port {self.port} occupied by unresponsive process, attempting cleanup")
        stale_pid = self._find_pid_on_port()
        if stale_pid:
            logger.info(f"Killing stale process (PID {stale_pid})")
            try:
                os.kill(stale_pid, signal.SIGTERM)
                for _ in range(10):
                    time.sleep(0.5)
                    if not self._is_port_in_use():
                        logger.info(f"Stale process (PID {stale_pid}) cleaned up")
                        return False
                if not _force_kill_pid(stale_pid):
                    return False
                time.sleep(1)
            except ProcessLookupError:
                pass
            except PermissionError:
                logger.error(f"No permission to kill stale process (PID {stale_pid})")
                return False

        # No listening process found but port still blocked — likely in TIME_WAIT
        # after our own subprocess was just stopped. Wait briefly for OS to release it.
        if self._is_port_in_use():
            logger.info(f"Port {self.port} appears to be in TIME_WAIT, waiting for OS to release it...")
            for _ in range(10):
                time.sleep(0.5)
                if not self._is_port_in_use():
                    logger.info(f"Port {self.port} released")
                    return False
            logger.error(f"Cannot free port {self.port}")
            return False

        return False

    def _find_pid_on_port(self) -> int | None:
        """Find the PID of a process listening on the configured port."""
        try:
            for conn in psutil.net_connections(kind="tcp"):
                if conn.laddr.port == self.port and conn.status == psutil.CONN_LISTEN:
                    return conn.pid
        except psutil.AccessDenied:
            pass
        return None

    def start(self) -> bool:
        """Start the Panel server subprocess."""
        if self.process and self.process.poll() is None:
            logger.info("Panel server is already running")
            return True

        if self._is_port_in_use():
            if self._try_recover_stale_server():
                return True
            if self._is_port_in_use():
                logger.error(f"Port {self.port} is still in use")
                return False

        try:
            app_path = Path(__file__).parent / "app.py"
            env = self._build_subprocess_env()

            logger.info(f"Starting Panel server on {self.host}:{self.port}")
            self.process = subprocess.Popen(
                [sys.executable, str(app_path)],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
            )

            if self._wait_for_health():
                logger.info("Panel server started successfully")
                self.restart_count = 0
                return True
            else:
                logger.error("Panel server failed to start (health check timed out)")
                self.stop()
                return False

        except Exception as e:
            logger.exception(f"Error starting Panel server: {e}")
            return False

    def _wait_for_health(self, timeout: int = 30, interval: float = 1.0) -> bool:
        start_time = time.time()
        base_url = f"http://{self.host}:{self.port}"

        while time.time() - start_time < timeout:
            try:
                response = requests.get(f"{base_url}/api/health", timeout=2)
                if response.status_code == 200:
                    return True
            except requests.RequestException:
                pass

            if self.process and self.process.poll() is not None:
                logger.error("Panel server process died during startup")
                self._log_startup_failure()
                return False

            time.sleep(interval)

        return False

    def is_healthy(self) -> bool:
        try:
            response = requests.get(f"http://{self.host}:{self.port}/api/health", timeout=2)
            return response.status_code == 200
        except requests.RequestException:
            return False

    def stop(self, timeout: int = 5) -> None:
        if not self.process:
            return
        try:
            logger.info("Stopping Panel server")
            self.process.terminate()
            try:
                self.process.wait(timeout=timeout)
                logger.info("Panel server stopped gracefully")
            except subprocess.TimeoutExpired:
                logger.warning("Panel server did not stop gracefully, killing")
                self.process.kill()
                self.process.wait()
        except Exception as e:
            logger.exception(f"Error stopping Panel server: {e}")
        finally:
            self.process = None

    def restart(self) -> bool:
        if self.restart_count >= self.max_restarts:
            logger.error(f"Maximum restart attempts ({self.max_restarts}) reached")
            return False
        self.restart_count += 1
        logger.info(f"Restarting Panel server (attempt {self.restart_count}/{self.max_restarts})")
        self.stop()
        return self.start()

    def get_base_url(self) -> str:
        return f"http://{self.host}:{self.port}"
