from collections import OrderedDict
from threading import Lock
from time import monotonic
from fastapi.responses import JSONResponse


class AuthThrottle:
    """Bounded per-process limiter; production ingress must limit across replicas."""
    def __init__(self, limit: int):
        self.limit = limit
        self.entries = OrderedDict()
        self.lock = Lock()

    def retry_after(self, key: str) -> int:
        now = monotonic()
        with self.lock:
            started, count = self.entries.pop(key, (now, 0))
            if now - started >= 60: started, count = now, 0
            blocked = count >= self.limit
            self.entries[key] = (started, count if blocked else count + 1)
            if len(self.entries) > 10000: self.entries.popitem(last=False)
            return max(1, int(60 - (now - started)) + 1) if blocked else 0


def install_auth_throttle(app, limit: int):
    throttle = AuthThrottle(limit)

    @app.middleware("http")
    async def limit_auth(request, call_next):
        if request.method == "POST" and request.url.path in {"/api/v1/auth/register", "/api/v1/auth/login"}:
            # Never trust a client-supplied X-Forwarded-For header here.
            key = request.client.host if request.client else "unknown"
            delay = throttle.retry_after(key)
            if delay:
                return JSONResponse(status_code=429, headers={"Retry-After": str(delay)},
                    content={"error": {"code": "rate_limited", "message": "Too many authentication attempts"}})
        response = await call_next(request)
        if request.url.path.startswith(("/api/v1/auth", "/api/v1/users", "/api/v1/admin")):
            response.headers["Cache-Control"] = "no-store"
        return response
