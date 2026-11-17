#!/usr/bin/env python3
"""Non-destructive HTTP acceptance checks for an explicitly supplied demo URL."""
import argparse
import json
import re
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_url", help="For example https://casa.salehmmrezaei.com")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    parsed = urlsplit(base)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.path:
        parser.error("Supply an origin URL without a path")

    def request(path, *, method="GET", token=None, body=None, expected=200):
        headers = {"Accept": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        data = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode()
        req = Request(base + path, data=data, headers=headers, method=method)
        try:
            response = urlopen(req, timeout=30)
        except HTTPError as exc:
            response = exc
        with response:
            payload = response.read()
            assert response.status == expected, f"{method} {path}: expected {expected}, got {response.status}"
            content_type = response.headers.get("Content-Type", "")
            return (json.loads(payload) if "application/json" in content_type else payload), response.headers

    home, headers = request("/")
    assert b'id="root"' in home, "React production index was not served"
    assert "default-src 'self'" in headers.get("Content-Security-Policy", ""), "CSP missing"
    assert headers.get("X-Content-Type-Options") == "nosniff", "Security header missing"
    script = re.search(rb'<script[^>]+src="([^"]+)"', home)
    assert script, "Built JavaScript asset missing"
    asset, _ = request(script.group(1).decode())
    assert len(asset) > 1000, "Production asset did not load"
    deep, _ = request("/tenant/assistant")
    assert deep == home, "SPA deep links did not serve index.html"
    request("/api/v1/health/ready")
    status, _ = request("/api/v1/demo/status")
    assert status["enabled"] and status["read_only"] and status["assistant_mode"] == "simulated"
    listings, _ = request("/api/v1/listings?page_size=2")
    assert listings["total"] >= 1 and listings["items"][0]["is_synthetic"]
    sample = listings["items"][0]
    assert sample["images"], "Synthetic listing images missing"
    photo, _ = request(sample["images"][0]["url"])
    assert len(photo) > 1000, "Sample photo failed to load"
    detail, _ = request("/listings/" + sample["id"])
    assert detail == home, "Listing detail refresh failed"

    tokens = {}
    for role, read_path in (("tenant", "/applications"), ("landlord", "/properties"), ("admin", "/admin/users")):
        session, _ = request("/api/v1/demo/access", method="POST", body={"role": role})
        tokens[role] = session["access_token"]
        assert session["user"]["role"] == role
        request("/api/v1" + read_path, token=tokens[role])
        request("/api/v1/users/me", method="PATCH", token=tokens[role], body={"full_name": "Synthetic smoke attempt"}, expected=403)
    request("/api/v1/admin/users", token=tokens["tenant"], expected=403)
    request("/api/v1/properties", token=tokens["tenant"], expected=403)
    request("/api/v1/applications", token=tokens["landlord"], expected=403)
    request("/api/v1/auth/register", method="POST", body={}, expected=403)
    request("/api/v1/auth/login", method="POST", body={}, expected=403)
    request("/api/v1/properties", method="POST", token=tokens["admin"], body={}, expected=403)
    request("/api/v1/conversations", method="POST", token=tokens["tenant"], body={}, expected=403)
    request("/api/v1/properties/00000000-0000-0000-0000-000000000000/images", method="POST", token=tokens["landlord"], body={}, expected=403)
    request("/api/v1/future-write-route", method="DELETE", token=tokens["admin"], expected=403)
    assistant, _ = request("/api/v1/assistant/status", token=tokens["tenant"])
    assert assistant["available"] and assistant["mode"] == "simulated"
    chat, _ = request("/api/v1/assistant/chat", method="POST", token=tokens["tenant"], body={"message": "Find rooms in Bologna under 700 euros"})
    assert "Simulated" in chat["messages"][-1]["content"]
    assert not chat["messages"][-1]["actions"], "Demo created a privileged action"
    second, _ = request("/api/v1/demo/access", method="POST", body={"role": "tenant"})
    other_token = second["access_token"]
    threads, _ = request("/api/v1/assistant/threads", token=other_token)
    assert threads == [], "Visitor chat histories leaked across sessions"
    request("/api/v1/auth/logout", method="POST", token=tokens["tenant"], expected=204)
    request("/api/v1/users/me", token=tokens["tenant"], expected=401)
    request("/api/v1/users/me", token=other_token)
    after, _ = request("/api/v1/listings?page_size=2")
    assert after == listings, "Shared sample listings changed"
    request("/docs", expected=404)
    request("/openapi.json", expected=404)
    print("PASS: production assets, proxy, deep links, images, three roles, isolation, write protection, simulated chat and logout.")
    print("This verifies the supplied URL only; inspect browser rendering, TLS, DNS and server recovery separately.")


if __name__ == "__main__":
    main()
