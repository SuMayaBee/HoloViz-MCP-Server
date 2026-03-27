"""REST API endpoints for the Display System.

Tornado RequestHandler classes for /api/snippet and /api/health.
"""

import json
import logging
import traceback
from datetime import datetime
from datetime import timezone

from tornado.web import RequestHandler

from holoviz_mcp_server.config import get_config
from holoviz_mcp_server.display.database import get_db
from holoviz_mcp_server.validation import SecurityError

logger = logging.getLogger(__name__)


def _get_external_base_url(request_host: str) -> str | None:
    try:
        return get_config().external_url or None
    except Exception:
        return None


class SnippetEndpoint(RequestHandler):
    """Tornado RequestHandler for POST /api/snippet."""

    def post(self):
        db = get_db()
        try:
            request_body = json.loads(self.request.body.decode("utf-8"))
            code = request_body.get("code", "")
            name = request_body.get("name", "")
            description = request_body.get("description", "")
            method = request_body.get("method", "jupyter")

            snippet = db.create_visualization(
                app=code,
                name=name,
                description=description,
                method=method,
            )

            if base_url := _get_external_base_url(self.request.host):
                url = f"{base_url}/view?id={snippet.id}"
            else:
                full_url = self.request.full_url()
                url = full_url.replace("/api/snippet", "/view?id=" + snippet.id)

            result = {"id": snippet.id, "url": url}
            if snippet.error_message:
                result["error_message"] = snippet.error_message

            self.set_status(200)
            self.set_header("Content-Type", "application/json")
            self.write(result)

        except SyntaxError as e:
            self.set_status(400)
            self.set_header("Content-Type", "application/json")
            self.write({"error": "SyntaxError", "message": str(e)})
        except SecurityError as e:
            self.set_status(400)
            self.set_header("Content-Type", "application/json")
            self.write({"error": "SecurityError", "message": str(e)})
        except ValueError as e:
            self.set_status(400)
            self.set_header("Content-Type", "application/json")
            self.write({"error": "ValueError", "message": str(e)})
        except Exception as e:
            logger.exception("Error in /api/snippet endpoint")
            self.set_status(500)
            self.set_header("Content-Type", "application/json")
            self.write(
                {
                    "error": "InternalError",
                    "message": str(e),
                    "traceback": traceback.format_exc(),
                }
            )


class HealthEndpoint(RequestHandler):
    """Tornado RequestHandler for GET /api/health."""

    def get(self):
        self.set_status(200)
        self.set_header("Content-Type", "application/json")
        self.write(
            {
                "status": "healthy",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
