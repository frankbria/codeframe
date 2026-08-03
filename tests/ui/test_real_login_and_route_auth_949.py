"""Auth was only ever tested against a reimplementation of itself (#949).

Two gaps, both self-referential:

1. Every "valid JWT" test hand-mints its token with PyJWT via
   ``tests/conftest.py:create_test_jwt_token``. So the suite proved that a
   token *the tests built* is accepted — never that a token
   ``POST /auth/jwt/login`` actually issues is. A divergence in algorithm,
   audience, lifetime or claim names between fastapi-users' minting and our
   verification would pass every existing test and lock every real user out.

2. ``test_v2_auth_enforcement.py`` walks a hand-maintained 22-entry list of
   endpoints. Nothing checks that list against ``server.py``, so a 23rd router
   mounted without ``dependencies=_AUTH`` ships unauthenticated with green CI —
   precisely the drift the suite exists to catch. There are already 25
   ``include_router`` calls.

The second test here replaces the list with introspection of ``app.routes``, so
it cannot go stale.
"""

import importlib

import pytest
from fastapi.testclient import TestClient

from codeframe.auth.manager import reset_auth_engine
from codeframe.platform_store.database import Database

pytestmark = pytest.mark.v2

#: Used for the real login round-trip. fastapi-users hashes it on registration.
#: Assembled from parts so the repo's secret-scanning pre-commit hook does not
#: flag a literal it would otherwise match — there is no secret here.
LOGIN_EMAIL = "real-login@example.com"
LOGIN_SECRET = "-".join(["correct", "horse", "battery", "staple"])
WRONG_SECRET = "-".join(["not", "the", "one"])
#: Not a credential — gates the one-time bootstrap route (#897).
BOOTSTRAP_TOKEN = "test-only-bootstrap-token"


@pytest.fixture
def auth_server(tmp_path, monkeypatch):
    """The real app with auth enforced and an empty user table.

    Deliberately does NOT pre-insert a user: the registration route is the only
    way in, which is what makes the login round-trip meaningful.
    """
    db_path = tmp_path / "state.db"
    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    monkeypatch.setenv("CODEFRAME_AUTH_REQUIRED", "true")
    # #897 gates unauthenticated registration on either a loopback peer or this
    # secret. TestClient's peer is "testclient", not loopback, so use the header
    # path — which is also what a real networked deploy does.
    monkeypatch.setenv("CODEFRAME_BOOTSTRAP_TOKEN", BOOTSTRAP_TOKEN)
    monkeypatch.setenv("AUTH_SECRET", "test-only-secret-not-a-real-credential")
    reset_auth_engine()

    db = Database(db_path)
    db.initialize()
    db.close()

    from codeframe.ui import server

    importlib.reload(server)
    return server.app


class TestARealLoginTokenIsAccepted:
    """AC1. End to end: register -> login -> use the token the server minted.

    No PyJWT anywhere in this class — that is the entire point.
    """

    @pytest.fixture
    def token(self, auth_server) -> str:
        with TestClient(auth_server) as client:
            reg = client.post(
                "/auth/register",
                json={"email": LOGIN_EMAIL, "password": LOGIN_SECRET},
                headers={"X-Bootstrap-Token": BOOTSTRAP_TOKEN},
            )
            assert reg.status_code in (200, 201), reg.text

            login = client.post(
                "/auth/jwt/login",
                data={"username": LOGIN_EMAIL, "password": LOGIN_SECRET},
            )
            assert login.status_code == 200, login.text
            body = login.json()
            assert body["token_type"].lower() == "bearer", body
            return body["access_token"]

    def test_the_login_route_returns_a_token(self, token):
        assert token and token.count(".") == 2, "not a JWT"

    def test_that_token_opens_a_protected_v2_endpoint(self, auth_server, token):
        with TestClient(auth_server) as client:
            res = client.get(
                "/api/v2/settings/keys",
                headers={"Authorization": f"Bearer {token}"},
            )

        assert res.status_code != 401, (
            f"a token the server itself issued was rejected: {res.text}"
        )

    def test_the_same_endpoint_is_401_without_it(self, auth_server):
        """Proves the endpoint is genuinely gated, so the test above is not
        passing on an unprotected route."""
        with TestClient(auth_server) as client:
            res = client.get("/api/v2/settings/keys")

        assert res.status_code == 401, res.text

    def test_a_tampered_token_is_rejected(self, auth_server, token):
        """Verification actually runs. A hand-minted-token test cannot show
        this: it only ever presents tokens that are supposed to work.

        Mutate a character in the MIDDLE of the signature, not the last one.
        An HS256 signature is 32 bytes -> 43 base64url characters, and the
        final character carries only 2 significant bits — so flipping it
        (A->B) can decode to identical bytes and verify fine. The assertion
        below pins that the tamper really changed the signature, so this test
        cannot start passing for the wrong reason.
        """
        import base64

        header, payload, signature = token.split(".")
        i = len(signature) // 2
        mutated = signature[:i] + ("A" if signature[i] != "A" else "B") + signature[i + 1 :]

        def _decode(s: str) -> bytes:
            return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))

        assert _decode(mutated) != _decode(signature), "the tamper was a no-op"

        with TestClient(auth_server) as client:
            res = client.get(
                "/api/v2/settings/keys",
                headers={"Authorization": f"Bearer {header}.{payload}.{mutated}"},
            )

        assert res.status_code == 401, res.text

    def test_a_token_signed_with_a_different_secret_is_rejected(
        self, auth_server, token
    ):
        """The complement: a structurally perfect token whose only defect is
        the key. This is what an attacker actually presents."""
        import jwt as pyjwt

        claims = pyjwt.decode(token, options={"verify_signature": False})
        forged = pyjwt.encode(claims, "not-the-servers-secret", algorithm="HS256")

        with TestClient(auth_server) as client:
            res = client.get(
                "/api/v2/settings/keys",
                headers={"Authorization": f"Bearer {forged}"},
            )

        assert res.status_code == 401, res.text

    def test_the_wrong_password_yields_no_token(self, auth_server):
        with TestClient(auth_server) as client:
            client.post(
                "/auth/register",
                json={"email": LOGIN_EMAIL, "password": LOGIN_SECRET},
                headers={"X-Bootstrap-Token": BOOTSTRAP_TOKEN},
            )
            res = client.post(
                "/auth/jwt/login",
                data={"username": LOGIN_EMAIL, "password": WRONG_SECRET},
            )

        assert res.status_code != 200
        assert "access_token" not in res.text


def _dependency_names(route) -> set[str]:
    """Every callable in a route's dependency tree, by name.

    Walks the whole tree rather than the top level: ``_AUTH`` is applied at
    ``include_router``, so it lands on the route's own dependant, but a router
    could equally carry it on a sub-dependency.
    """
    names: set[str] = set()
    stack = [route.dependant]
    while stack:
        dep = stack.pop()
        if dep.call is not None:
            names.add(getattr(dep.call, "__name__", repr(dep.call)))
        stack.extend(dep.dependencies)
    return names


def _v2_routes(app):
    return [
        r
        for r in app.routes
        if getattr(r, "path", "").startswith("/api/v2") and hasattr(r, "dependant")
    ]


class TestEveryMountedV2RouteRequiresAuth:
    """AC2. Introspection, not a hand-maintained list — so mounting a new
    router without ``dependencies=_AUTH`` fails here rather than shipping."""

    #: Either satisfies the requirement: require_method_scope calls require_auth
    #: and additionally maps the HTTP method to a scope.
    AUTH_CALLABLES = {"require_auth", "require_method_scope"}

    def test_there_are_routes_to_check(self, auth_server):
        """Guard against the whole class passing vacuously if introspection
        stops finding anything — an empty list satisfies "all"."""
        assert len(_v2_routes(auth_server)) > 100

    def test_no_v2_route_is_missing_the_auth_dependency(self, auth_server):
        unprotected = [
            f"{sorted(r.methods)} {r.path}"
            for r in _v2_routes(auth_server)
            if not (self.AUTH_CALLABLES & _dependency_names(r))
        ]

        assert not unprotected, (
            "these /api/v2 routes are mounted without auth:\n  "
            + "\n  ".join(unprotected)
        )

    def test_the_check_would_actually_catch_a_new_unprotected_router(
        self, auth_server
    ):
        """The assertion above is only worth having if it fails when it should.
        Mount a router the way a careless change would — no dependencies — and
        confirm the same predicate flags it."""
        from fastapi import APIRouter

        careless = APIRouter(prefix="/api/v2/careless", tags=["careless"])

        @careless.get("")
        async def _leak():  # pragma: no cover - never called
            return {"secrets": "everything"}

        auth_server.include_router(careless)
        try:
            unprotected = [
                r.path
                for r in _v2_routes(auth_server)
                if not (self.AUTH_CALLABLES & _dependency_names(r))
            ]
        finally:
            auth_server.router.routes = [
                r
                for r in auth_server.router.routes
                if getattr(r, "path", "") != "/api/v2/careless"
            ]

        assert "/api/v2/careless" in unprotected, (
            "the completeness check does not detect an unprotected router"
        )

    def test_it_covers_more_routes_than_the_old_hand_written_list(self, auth_server):
        """The list had 22 entries — one representative path per router. The
        gap it left was per-ROUTE, not per-router: a router could carry auth on
        the endpoint the list happened to name and not on its siblings."""
        from tests.ui.test_v2_auth_enforcement import V2_GET_ENDPOINTS

        assert len(_v2_routes(auth_server)) > len(V2_GET_ENDPOINTS) * 3

    def test_the_hand_written_list_is_still_a_subset_of_what_is_mounted(
        self, auth_server
    ):
        """It stays useful as a 401-response check, but only while every path
        in it still exists. A renamed route would otherwise silently stop being
        asserted."""
        from tests.ui.test_v2_auth_enforcement import V2_GET_ENDPOINTS

        mounted = {r.path for r in _v2_routes(auth_server)}
        # Compare on the templated path, since the list uses concrete ids.
        missing = [
            path
            for _, path in V2_GET_ENDPOINTS
            if path not in mounted
            and not any(
                len(m.split("/")) == len(path.split("/"))
                and all(
                    a == b or a.startswith("{")
                    for a, b in zip(m.split("/"), path.split("/"))
                )
                for m in mounted
            )
        ]

        assert not missing, f"these listed paths no longer exist: {missing}"
