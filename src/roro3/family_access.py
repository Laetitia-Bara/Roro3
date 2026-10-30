"""Accès familial local : code privé et session signée, HTTP et WebSocket.

Ce module ne transporte aucun identifiant de plateforme. Le réseau local doit être
de confiance : HTTP ne chiffre pas les échanges. Aucun relais Internet n'est créé.
"""

import hashlib
import hmac
import ipaddress
import json
import re
import secrets
import socket
import time
from collections.abc import Awaitable, Callable, Sequence
from http.cookies import CookieError, SimpleCookie
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

_NETWORKS = tuple(
    ipaddress.ip_network(net)
    for net in (
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "127.0.0.0/8",
    )
)
_COOKIE = "roro_family"
_LOGIN = "/_family/login"
_LIFETIME = 12 * 60 * 60

type Scope = dict[str, Any]
type Receive = Callable[[], Awaitable[dict[str, Any]]]
type Send = Callable[[dict[str, Any]], Awaitable[None]]
type ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]


def private_ipv4(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    return address.version == 4 and any(address in net for net in _NETWORKS)


def family_host(explicit: str | None = None) -> str:
    if explicit:
        if not private_ipv4(explicit):
            raise ValueError("Choisissez une adresse IPv4 privée de cet ordinateur.")
        return explicit
    candidates = [
        item[4][0]
        for item in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)
        if private_ipv4(item[4][0]) and not item[4][0].startswith("127.")
    ]
    if not candidates:
        raise ValueError("Adresse locale introuvable. Indiquez --host avec l'IPv4 privée du PC.")
    return candidates[0]


def load_access_code(path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8") as stream:
            json.dump({"access_code": secrets.token_urlsafe(24)}, stream, indent=2)
    except FileExistsError:
        pass
    # Ne pas remplacer un fichier invalide et déconnecter les appareils en silence.
    try:
        code = json.loads(path.read_text(encoding="utf-8"))["access_code"]
        if not isinstance(code, str) or not re.fullmatch(r"[A-Za-z0-9_-]{24,128}", code):
            raise ValueError
    except (ValueError, KeyError, TypeError) as error:
        raise ValueError("Le fichier du code familial est invalide.") from error
    return code


class FamilyAccessMiddleware:
    """Le mur d'accès couvre aussi les transports Socket.IO et leurs ressources."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        access_code: str,
        authority: str,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.app, self.authority, self.clock = app, authority, clock
        self.key = hashlib.sha256(access_code.encode()).digest()
        self.failures: dict[str, tuple[int, float]] = {}

    def token(self) -> str:
        issued = str(int(self.clock()))
        signature = hmac.new(self.key, issued.encode(), hashlib.sha256).hexdigest()
        return f"{issued}.{signature}"

    def authenticated(self, header: str) -> bool:
        try:
            cookie = SimpleCookie(header)
            value = cookie[_COOKIE].value
            issued, signature = value.split(".")
            age = self.clock() - int(issued)
            expected = hmac.new(self.key, issued.encode(), hashlib.sha256).hexdigest()
            return -5 <= age < _LIFETIME and hmac.compare_digest(signature, expected)
        except (CookieError, KeyError, ValueError, TypeError):
            return False

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return
        headers = {
            k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])
        }
        peer = scope.get("client") or ("", 0)
        origin = headers.get("origin")
        scheme = "https" if scope.get("scheme") in {"https", "wss"} else "http"
        valid_origin = origin == f"{scheme}://{self.authority}"
        if (
            not private_ipv4(peer[0])
            or headers.get("host") != self.authority
            or (origin is not None and not valid_origin)
            or (scope["type"] == "websocket" and not valid_origin)
        ):
            await self._deny(scope, send, 403)
            return
        if scope["type"] == "http" and scope["path"] == _LOGIN:
            await self._login(scope, headers, peer[0], receive, send, valid_origin)
            return
        if not self.authenticated(headers.get("cookie", "")):
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 1008})
            else:
                await self._response(send, 303, b"", [(b"location", _LOGIN.encode())])
            return
        if scope["type"] == "websocket":
            expired = False

            async def session_receive() -> dict[str, Any]:
                nonlocal expired
                if expired:
                    return {"type": "websocket.disconnect", "code": 1008}
                message = await receive()
                if message["type"] != "websocket.disconnect" and not self.authenticated(
                    headers.get("cookie", "")
                ):
                    expired = True
                    await send({"type": "websocket.close", "code": 1008})
                    return {"type": "websocket.disconnect", "code": 1008}
                return message

            await self.app(scope, session_receive, send)
        else:
            await self.app(scope, receive, send)

    async def _deny(self, scope: Scope, send: Send, status: int) -> None:
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
        else:
            await self._response(send, status, b"Acces refuse.")

    async def _login(
        self,
        scope: Scope,
        headers: dict[str, str],
        peer: str,
        receive: Receive,
        send: Send,
        valid_origin: bool,
    ) -> None:
        error = ""
        if scope["method"] == "POST":
            if not valid_origin:
                await self._response(send, 403, b"Origine invalide.")
                return
            count, started = self.failures.get(peer, (0, self.clock()))
            if self.clock() - started >= 60:
                count, started = 0, self.clock()
            if count >= 5:
                await self._response(send, 429, b"Attendez une minute avant un nouvel essai.")
                return
            body = b""
            while True:
                message = await receive()
                if message["type"] != "http.request":
                    return
                body += message.get("body", b"")
                if len(body) > 4096:
                    await self._response(send, 413, b"Formulaire trop long.")
                    return
                if not message.get("more_body", False):
                    break
            try:
                values = parse_qs(body.decode(), max_num_fields=4)
                supplied = values.get("code", [""])[0]
            except (ValueError, UnicodeError):
                supplied = ""
            if hmac.compare_digest(hashlib.sha256(supplied.encode()).digest(), self.key):
                self.failures.pop(peer, None)
                cookie = (
                    f"{_COOKIE}={self.token()}; Path=/; HttpOnly; SameSite=Strict; "
                    f"Max-Age={_LIFETIME}" + ("; Secure" if scope["scheme"] == "https" else "")
                )
                await self._response(
                    send,
                    303,
                    b"",
                    [
                        (b"location", b"/"),
                        (b"set-cookie", cookie.encode()),
                    ],
                )
                return
            if len(self.failures) >= 256:
                self.failures.pop(next(iter(self.failures)))
            self.failures[peer] = (count + 1, started)
            error = "Code incorrect."
        elif scope["method"] != "GET":
            await self._response(send, 405, b"Methode invalide.")
            return
        html = f"""<!doctype html><html lang="fr"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Roro · Accès familial</title><style>
body{{margin:0;background:#f7f5ef;color:#243b31;font:17px system-ui}}
main{{max-width:420px;margin:12vh auto;padding:28px}}h1{{font-size:32px}}
input,button{{box-sizing:border-box;width:100%;font:inherit;padding:15px;margin:12px 0;
border:1px solid #bccdbd;border-radius:12px}}button{{background:#3f6e5a;color:white}}
p{{line-height:1.6}}.error{{color:#a94b48}}</style><main><p>RORO · FAMILLE</p>
<h1>Bienvenue à la maison.</h1><p>Saisissez le code d'accès conservé sur l'ordinateur
qui héberge Roro. Ce code est distinct de votre compte Too Good To Go.</p>
<form method="post" action="{_LOGIN}"><label for="code">Code familial</label>
<input id="code" name="code" type="password" required maxlength="128"
autocomplete="current-password"><button>Ouvrir Roro</button></form>
<p class="error">{error}</p><p>Accès sur votre réseau privé. Le serveur doit rester allumé.</p>
</main></html>"""
        await self._response(send, 200 if not error else 401, html.encode())

    @staticmethod
    async def _response(
        send: Send,
        status: int,
        body: bytes,
        extra: Sequence[tuple[bytes, bytes]] = (),
    ) -> None:
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [
                    (b"content-type", b"text/html; charset=utf-8"),
                    (b"cache-control", b"no-store"),
                    (b"x-frame-options", b"DENY"),
                    (b"referrer-policy", b"same-origin"),
                    *extra,
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
