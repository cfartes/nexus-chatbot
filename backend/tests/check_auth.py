import asyncio
import json
from http.cookies import SimpleCookie
from unittest.mock import patch

from starlette.types import Message, Scope

from src.main import app

ORIGIN = "https://nexus.example.test"
LOGIN = b'{"tenant_id":"00000000-0000-0000-0000-000000000001","email":"ADMIN@example.test","password":"test-password-123"}'
SESSION_PATH = "/sessions/00000000-0000-0000-0000-000000000003"
QR_PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jH2sAAAAASUVORK5CYII="


async def request(
    method: str, path: str, body: bytes = b"", headers: tuple[tuple[bytes, bytes], ...] = (),
    *, prefix: str = "auth", query: bytes = b"",
) -> tuple[int, list[tuple[bytes, bytes]], bytes]:
    events: list[Message] = []
    scope: Scope = {
        "type": "http", "method": method, "path": f"/api/v1/{prefix}" + (f"/{path}" if path else ""),
        "headers": [(b"content-type", b"application/json"), *headers],
        "query_string": query, "scheme": "https", "client": ("127.0.0.1", 1234),
    }

    async def receive() -> Message:
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(event: Message) -> None:
        events.append(event)

    await app(scope, receive, send)
    return events[0]["status"], events[0]["headers"], events[1]["body"]


async def check() -> None:
    origin = (b"origin", ORIGIN.encode())
    async with app.router.lifespan_context(app):
        assert (await request("POST", "login", LOGIN))[0] == 403
        status, _, invalid = await request("POST", "login", b'{"password":"do-not-echo"}', (origin,))
        assert status == 422 and b"do-not-echo" not in invalid
        status, headers, body = await request("POST", "login", LOGIN, (origin,))
        assert status == 200 and json.loads(body)["role"] == "admin", (status, body)
        cookies = SimpleCookie()
        for name, value in headers:
            if name == b"set-cookie":
                cookies.load(value.decode())
        session = cookies["nexus_atende_session"]
        assert session["httponly"] and session["secure"]
        cookie = (b"cookie", f"nexus_atende_session={session.value}".encode())
        csrf = (b"x-csrf-token", cookies["nexus_atende_csrf"].value.encode())
        assert (await request("GET", "me", headers=(cookie,)))[0] == 200
        await check_whatsapp(cookie)
        assert (await request("POST", "logout", headers=(origin, cookie)))[0] == 403
        assert (await request("POST", "logout", headers=(origin, cookie, csrf)))[0] == 204
        assert (await request("GET", "me", headers=(cookie,)))[0] == 401
        for _ in range(4):
            assert (await request("POST", "login", LOGIN.replace(b"test-password-123", b"wrong"), (origin,)))[0] == 401
        assert (await request("POST", "login", LOGIN, (origin,)))[0] == 429


async def check_whatsapp(cookie: tuple[bytes, bytes]) -> None:
    endpoint = "connection/qr"
    assert (await request("GET", endpoint, prefix="whatsapp"))[0] == 401
    with patch("src.services.openwa.OpenWAClient._read", side_effect=[{"status": "ready"}]) as read:
        status, _, body = await request("GET", "connection", headers=(cookie,), prefix="whatsapp")
        assert status == 200 and json.loads(body)["status"] == "READY", (status, body)
        read.assert_called_once_with(SESSION_PATH)
    with patch("src.services.openwa.OpenWAClient._read", side_effect=[{"status": "QR_READY"}, {"qrCode": QR_PNG}]) as read:
        status, headers, body = await request("GET", endpoint, headers=(cookie,), prefix="whatsapp")
        assert status == 200 and json.loads(body)["qr_code"] == f"data:image/png;base64,{QR_PNG}"
        assert (b"cache-control", b"no-store") in headers
        assert [call.args for call in read.call_args_list] == [(SESSION_PATH,), (f"{SESSION_PATH}/qr",)]
    with patch("src.services.openwa.OpenWAClient._read", side_effect=[{"status": "QR_READY"}, {"qrCode": "PHN2Zy8+"}]):
        assert (await request("GET", endpoint, headers=(cookie,), prefix="whatsapp"))[0] == 502


if __name__ == "__main__":
    asyncio.run(check())
