import hmac
import time
from hashlib import sha256
from secrets import token_hex
from typing import Generator

import httpx

AUTH_SCHEME = "VERACODE-HMAC-SHA-256"
REQUEST_VERSION = b"vcode_request_version_1"


def _compute_signature(
    api_secret: str, signing_data: str, timestamp: str, nonce: str
) -> str:
    key_nonce = hmac.new(
        bytes.fromhex(api_secret), bytes.fromhex(nonce), sha256
    ).digest()
    key_date = hmac.new(key_nonce, timestamp.encode(), sha256).digest()
    signature_key = hmac.new(key_date, REQUEST_VERSION, sha256).digest()
    return hmac.new(signature_key, signing_data.encode(), sha256).hexdigest()


class VeracodeHMACAuth(httpx.Auth):
    """Implements Veracode's HMAC-SHA-256 request signing for httpx."""

    def __init__(self, api_id: str, api_secret: str):
        self.api_id = api_id
        self.api_secret = api_secret

    def auth_flow(
        self, request: httpx.Request
    ) -> Generator[httpx.Request, httpx.Response, None]:
        host = request.url.host
        # raw_path includes the query string, as required by Veracode
        path = request.url.raw_path.decode()
        method = request.method.upper()
        signing_data = f"id={self.api_id}&host={host}&url={path}&method={method}"
        timestamp = str(int(time.time() * 1000))
        nonce = token_hex(16)
        signature = _compute_signature(
            self.api_secret, signing_data, timestamp, nonce
        )
        request.headers["Authorization"] = (
            f"{AUTH_SCHEME} id={self.api_id},"
            f"ts={timestamp},nonce={nonce},sig={signature}"
        )
        yield request
