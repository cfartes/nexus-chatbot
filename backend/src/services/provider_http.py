from json import dumps, loads
from urllib.request import HTTPRedirectHandler, Request, build_opener


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(
        self, req: Request, fp: object, code: int, msg: str, headers: object, newurl: str,
    ) -> None:
        return None


def request_json(url: str, headers: dict[str, str], payload: object = None) -> object:
    body = None if payload is None else dumps(payload).encode()
    request = Request(url, data=body, headers={"Content-Type": "application/json", **headers})
    with build_opener(NoRedirect()).open(request, timeout=15) as response:
        raw = response.read(1_000_001)
    if len(raw) > 1_000_000:
        raise ValueError("Provider response exceeds the size limit")
    return loads(raw)
