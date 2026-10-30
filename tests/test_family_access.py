"""Vérifier les requêtes ASGI sans ouvrir de port réseau."""

from urllib.parse import urlencode

import pytest

from roro3.family_access import FamilyAccessMiddleware, family_host, load_access_code, private_ipv4

CODE = "a-private-code-for-family-tests-only"
AUTHORITY = "127.0.0.1:8764"


def request(
    middleware, path="/", method="GET", headers=None, body=b"", kind="http", peer="192.168.1.2"
):
    scope = {
        "type": kind,
        "path": path,
        "method": method,
        "scheme": "http",
        "client": (peer, 1234),
        "headers": [
            (b"host", AUTHORITY.encode()),
            *[(k.encode(), v.encode()) for k, v in (headers or {}).items()],
        ],
    }
    sent = []

    async def receive():
        return {"type": "http.request", "body": body}

    async def send(message):
        sent.append(message)

    # Ces coroutines ASGI ne suspendent que vers receive/send ci-dessus. Les
    # dérouler directement évite même la socket interne d'une boucle Windows.
    coroutine = middleware(scope, receive, send)
    try:
        coroutine.send(None)
    except StopIteration:
        pass
    else:
        coroutine.close()
        raise AssertionError("Une véritable attente inattendue nécessite un test adapté")
    return sent


def wall(clock=lambda: 1000):
    async def downstream(scope, receive, send):
        await send({"type": "downstream"})

    return FamilyAccessMiddleware(downstream, access_code=CODE, authority=AUTHORITY, clock=clock)


@pytest.mark.parametrize("path", ["/", "/history", "/_nicegui/anything", "/socket.io/"])
def test_all_http_app_surfaces_require_a_session(path):
    sent = request(wall(), path)
    assert sent[0]["status"] == 303
    assert (b"location", b"/_family/login") in sent[0]["headers"]


def test_successful_login_cookie_is_signed_and_protects_websocket():
    middleware = wall()
    sent = request(
        middleware,
        "/_family/login",
        "POST",
        {"origin": "http://" + AUTHORITY},
        urlencode({"code": CODE}).encode(),
    )
    assert sent[0]["status"] == 303
    cookie = dict(sent[0]["headers"])[b"set-cookie"].decode()
    assert "HttpOnly" in cookie and "SameSite=Strict" in cookie
    assert CODE not in cookie
    assert request(middleware, headers={"cookie": cookie}) == [{"type": "downstream"}]
    assert request(
        middleware, headers={"cookie": cookie, "origin": "http://" + AUTHORITY}, kind="websocket"
    ) == [{"type": "downstream"}]
    assert (
        request(middleware, kind="websocket", headers={"origin": "http://" + AUTHORITY})[0]["type"]
        == "websocket.close"
    )
    assert (
        request(
            middleware,
            kind="websocket",
            headers={"cookie": cookie, "origin": "https://evil.invalid"},
        )[0]["type"]
        == "websocket.close"
    )


def test_expired_tampered_and_future_cookie_are_rejected():
    now = [1000]
    middleware = wall(lambda: now[0])
    token = middleware.token()
    assert middleware.authenticated("roro_family=" + token)
    assert not middleware.authenticated("roro_family=" + token + "0")
    now[0] += 43200
    assert not middleware.authenticated("roro_family=" + token)
    now[0] = 900
    assert not middleware.authenticated("roro_family=" + token)
    assert not wall().authenticated("roro_family=bad.cookie")


def test_cross_origin_login_and_public_peer_cannot_reach_app():
    assert (
        request(wall(), "/_family/login", "POST", {"origin": "https://evil.invalid"})[0]["status"]
        == 403
    )
    assert request(wall(), peer="8.8.8.8")[0]["status"] == 403


def test_other_host_is_rejected_even_with_a_valid_cookie():
    middleware = wall()
    cookie = "roro_family=" + middleware.token()
    assert (
        request(middleware, headers={"host": "evil.invalid", "cookie": cookie})[0]["status"] == 403
    )


def test_an_open_websocket_stops_receiving_actions_after_session_expiry():
    now = [1000]
    received = []

    async def downstream(scope, receive, send):
        received.append(await receive())
        now[0] += 43200
        received.append(await receive())

    middleware = FamilyAccessMiddleware(
        downstream, access_code=CODE, authority=AUTHORITY, clock=lambda: now[0]
    )
    cookie = "roro_family=" + middleware.token()
    sent = request(
        middleware,
        kind="websocket",
        headers={
            "cookie": cookie,
            "origin": "http://" + AUTHORITY,
        },
    )
    assert received[-1] == {"type": "websocket.disconnect", "code": 1008}
    assert sent == [{"type": "websocket.close", "code": 1008}]


def test_failed_logins_are_rate_limited_and_window_expires():
    now = [1000]
    middleware = wall(lambda: now[0])
    for _ in range(5):
        assert (
            request(
                middleware,
                "/_family/login",
                "POST",
                {"origin": "http://" + AUTHORITY},
                b"code=wrong",
            )[0]["status"]
            == 401
        )
    assert (
        request(middleware, "/_family/login", "POST", {"origin": "http://" + AUTHORITY})[0][
            "status"
        ]
        == 429
    )
    now[0] += 61
    assert (
        request(
            middleware, "/_family/login", "POST", {"origin": "http://" + AUTHORITY}, b"code=wrong"
        )[0]["status"]
        == 401
    )


def test_private_access_file_is_stable_and_invalid_file_is_not_overwritten(tmp_path):
    path = tmp_path / "private" / "family-access.json"
    code = load_access_code(path)
    assert load_access_code(path) == code
    assert len(code) >= 24
    path.write_text('{"access_code":"invalid"}', encoding="utf-8")
    before = path.read_bytes()
    with pytest.raises(ValueError):
        load_access_code(path)
    assert path.read_bytes() == before


@pytest.mark.parametrize("host", ["0.0.0.0", "8.8.8.8", "example.com", "::1"])
def test_binding_to_public_or_all_interfaces_is_rejected(host):
    assert not private_ipv4(host)
    with pytest.raises(ValueError):
        family_host(host)
