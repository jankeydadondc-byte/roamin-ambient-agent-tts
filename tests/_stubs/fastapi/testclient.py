"""Simple TestClient implementation for stub FastAPI."""

from typing import Any, Dict


class Response:
    def __init__(self, status_code: int, json_data: Dict[str, Any] | None = None):
        self.status_code = status_code
        self._json_data = json_data or {}

    def json(self) -> Dict[str, Any]:
        return self._json_data


class TestClient:
    """Context manager that allows calling FastAPI handlers via app.routes."""

    def __init__(self, app):
        self.app = app

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, tb):
        pass

    def _invoke(self, handler, headers: Dict[str, str] | None, json_payload):
        # Try calling with both possible signatures
        try:
            return handler(headers=headers or {}, json=json_payload)
        except Exception:
            try:
                return handler(json=json_payload)
            except Exception:
                return handler()

    def _call_handler(self, method: str, path: str, json_payload=None, headers=None) -> Response:
        # Find matching route
        handler = None
        for route_key, func in self.app.routes.items():
            r_path, r_method = route_key
            if r_method != method.upper():
                continue
            # Simple pattern match: allow '{param}' as prefix/suffix
            if "{" in r_path:
                prefix, suffix = r_path.split("{", 1)[0], r_path.rsplit("}", 1)[-1]
                if path.startswith(prefix) and path.endswith(suffix):
                    handler = func
                    result = self._invoke(handler, headers=headers or {}, json_payload=json_payload)
                    return self._wrap_response(result)
            elif r_path == path:
                handler = func
                break
        if handler is None:
            return Response(404)
        try:
            result = self._invoke(handler, headers=headers or {}, json_payload=json_payload)
            return self._wrap_response(result)
        except Exception as e:
            # Return 500 for unexpected errors
            return Response(500, {"error": str(e)})

    def _wrap_response(self, res):
        if isinstance(res, Response):
            return res
        # Detect install plugin response
        if isinstance(res, dict) and "task_id" in res:
            return Response(202, res)
        # Assume dict -> success 200
        return Response(200, res)

    def get(self, path: str, headers=None):
        return self._call_handler("GET", path, headers=headers)

    def post(self, path: str, json=None, headers=None):
        return self._call_handler("POST", path, json_payload=json, headers=headers)
