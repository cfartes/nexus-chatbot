import asyncio
import json
from http.cookies import SimpleCookie

from src.main import app
from tests.check_auth import LOGIN, ORIGIN, request

ORIGIN_HEADER = (b"origin", ORIGIN.encode())


async def login(email: bytes) -> tuple[str, tuple[tuple[bytes, bytes], ...]]:
    status, headers, body = await request("POST", "login", LOGIN.replace(b"ADMIN@example.test", email), (ORIGIN_HEADER,))
    assert status == 200, (status, body)
    cookies = SimpleCookie()
    for name, value in headers:
        if name == b"set-cookie":
            cookies.load(value.decode())
    return json.loads(body)["id"], (
        (b"cookie", f"nexus_atende_session={cookies['nexus_atende_session'].value}".encode()),
        (b"x-csrf-token", cookies["nexus_atende_csrf"].value.encode()),
        ORIGIN_HEADER,
    )


async def check() -> None:
    async with app.router.lifespan_context(app):
        _, admin = await login(b"ADMIN@EXAMPLE.TEST")
        first_id, first = await login(b"FIRST@EXAMPLE.TEST")
        second_id, second = await login(b"SECOND@EXAMPLE.TEST")

        async def call(
            method: str, path: str, actor: tuple[tuple[bytes, bytes], ...],
            body: bytes = b"", query: bytes = b"",
        ) -> tuple[int, bytes]:
            status, _, payload = await request(method, path, body, actor, prefix="conversations", query=query)
            return status, payload

        status, payload = await call("GET", "", first)
        assert status == 200 and len(json.loads(payload)) == 1, (status, payload)
        conversation_id = json.loads(payload)[0]["id"]
        history_path = f"{conversation_id}/messages"
        status, latest = await call("GET", history_path, first, query=b"limit=1")
        assert status == 200 and len(json.loads(latest)) == 1
        cursor = json.loads(latest)[0]["id"]
        status, older = await call("GET", history_path, first, query=f"before={cursor}".encode())
        assert status == 200 and len(json.loads(older)) == 1
        assert (await call("POST", f"{conversation_id}/claim", (first[0], ORIGIN_HEADER)))[0] == 403

        first_claim, second_claim = await asyncio.gather(
            call("POST", f"{conversation_id}/claim", first), call("POST", f"{conversation_id}/claim", second),
        )
        assert sorted((first_claim[0], second_claim[0])) == [204, 409], (first_claim, second_claim)
        winner, loser = (first, second) if first_claim[0] == 204 else (second, first)
        winner_id, loser_id = (first_id, second_id) if first_claim[0] == 204 else (second_id, first_id)
        assert (await call("GET", history_path, winner))[0] == 200
        assert (await call("GET", history_path, loser))[0] == 404
        assert json.loads((await call("GET", "", winner, query=b"queue=mine"))[1])[0]["assigned_user_id"] == winner_id
        assert (await call("GET", "", winner, query=b"queue=assigned"))[0] == 403
        assert (await call("GET", "", winner, query=b"queue=closed"))[0] == 403
        status, counts = await call("GET", "counts", admin)
        assert status == 200 and json.loads(counts)["assigned"] == 1 and json.loads(counts)["closed"] == 0
        assert (await call("GET", "", admin, query=b"queue=assigned"))[0] == 200
        transfer_path = f"{conversation_id}/transfer"
        target = json.dumps({"user_id": loser_id}).encode()
        assert (await call("GET", "operators", winner))[0] == 200
        assert (await call("POST", transfer_path, loser, target))[0] == 409
        assert (await call("POST", transfer_path, winner, target))[0] == 204
        status, notices = await call("GET", "transfer-notices", loser)
        assert status == 200
        notice, = json.loads(notices)
        assert notice["conversation_id"] == conversation_id
        assert json.loads((await call("GET", "transfer-notices", winner))[1]) == []
        assert (await call("DELETE", f"transfer-notices/{notice['id']}", winner))[0] == 204
        assert json.loads((await call("GET", "transfer-notices", loser))[1]) == [notice]
        assert (await call("DELETE", f"transfer-notices/{notice['id']}", loser))[0] == 204
        assert json.loads((await call("GET", "transfer-notices", loser))[1]) == []
        assert (await call("POST", transfer_path, admin, json.dumps({"user_id": winner_id}).encode()))[0] == 204
        assert (await call("POST", transfer_path, admin, target))[0] == 204
        assert (await call("GET", history_path, winner))[0] == 404
        assert (await call("GET", history_path, loser))[0] == 200


if __name__ == "__main__":
    asyncio.run(check())
