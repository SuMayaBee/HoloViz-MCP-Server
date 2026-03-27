"""HTTP client for Display Server REST API."""

import logging

import requests

logger = logging.getLogger(__name__)


class DisplayClient:
    """HTTP client for Display Server REST API."""

    def __init__(self, base_url: str, timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()

    def is_healthy(self) -> bool:
        try:
            response = self.session.get(f"{self.base_url}/api/health", timeout=2)
            return response.status_code == 200
        except requests.RequestException:
            return False

    def create_snippet(self, code: str, name: str = "", description: str = "", method: str = "jupyter") -> dict:
        """Create a visualization snippet on the Display Server."""
        try:
            response = self.session.post(
                f"{self.base_url}/api/snippet",
                json={
                    "code": code,
                    "name": name,
                    "description": description,
                    "method": method,
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.exception(f"Error creating visualization: {e}")
            raise RuntimeError(f"Failed to create visualization: {e}") from e

    def close(self) -> None:
        if self.session:
            self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
