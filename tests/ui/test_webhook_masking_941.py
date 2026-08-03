"""The stored webhook URL is a secret, and the unsafe send path is gone (#941).

`GET /api/v2/settings/notifications` returned the stored webhook URL **verbatim
to any read-scope caller** — while the codebase itself treats these as secrets
(`redact_webhook_url` exists precisely because Slack/Discord/GitHub webhook URLs
embed tokens in their path). Every sibling secret here is admin-gated and never
echoed.

Separately, `send_blocker_notification` + `format_payload` had no production
callers but remained public and POSTed with a plain aiohttp session — no host
vetting, no pinned resolver, `allow_redirects` defaulting to True — bypassing
the #656/#746 hardening that `send_event` implements.
"""

import inspect

import pytest

from codeframe.core.notifications_config import redact_webhook_url

pytestmark = pytest.mark.v2

#: A Slack-shaped URL: the token is in the PATH, which is the whole problem.
SECRET_URL = "https://hooks.slack.com/services/T00000000/B11111111/XXXXsecretTOKEN"


class TestUrlIsMasked:
    def test_path_and_query_never_survive(self):
        masked = redact_webhook_url(SECRET_URL + "?signature=deadbeef")

        assert "XXXXsecretTOKEN" not in masked
        assert "T00000000" not in masked
        assert "deadbeef" not in masked
        assert masked == "https://hooks.slack.com"

    def test_basic_auth_credentials_are_stripped(self):
        masked = redact_webhook_url("https://user:hunter2@hooks.example.com/x")

        assert "hunter2" not in masked
        assert "user" not in masked

    def test_the_port_survives_because_it_is_not_secret(self):
        assert redact_webhook_url("https://h.example.com:8443/p?q=1") == (
            "https://h.example.com:8443"
        )

    def test_unparseable_input_does_not_leak_it_back(self):
        assert redact_webhook_url("not a url") == "<unparseable>"


class TestSettingsResponseDoesNotDiscloseTheUrl:
    def test_the_handler_masks_before_responding(self):
        from codeframe.ui.routers import settings_v2

        source = inspect.getsource(settings_v2.get_notification_settings)

        assert "redact_webhook_url(" in source
        assert 'webhook_url=cfg["webhook_url"]' not in source, (
            "the raw stored URL is still returned"
        )

    def test_the_response_model_exposes_a_set_flag(self):
        """So the UI can say 'configured' without being told the value."""
        from codeframe.ui.routers.settings_v2 import NotificationSettingsResponse

        assert "webhook_url_set" in NotificationSettingsResponse.model_fields

    def test_a_masked_response_still_identifies_the_destination(self):
        """Masking must not make the setting unverifiable by its owner."""
        masked = redact_webhook_url(SECRET_URL)

        assert "hooks.slack.com" in masked


class TestUnsafeSendPathIsGone:
    """AC2 — deleted rather than routed, since nothing called them."""

    @pytest.mark.parametrize("name", ["send_blocker_notification", "format_payload"])
    def test_method_no_longer_exists(self, name: str):
        from codeframe.notifications.webhook import WebhookNotificationService

        assert not hasattr(WebhookNotificationService, name), (
            f"{name} still exists and bypasses send_event's SSRF guards"
        )

    def test_the_module_has_no_unvetted_post(self):
        """Every remaining POST must go through the vetted, pinned path."""
        from codeframe.notifications import webhook

        source = inspect.getsource(webhook)
        # Strip comments so the deletion note explaining the old call does not
        # register as a live call site.
        code = "\n".join(line.split("#")[0] for line in source.splitlines())

        assert "session.post(" not in code or "allow_redirects=False" in code

    def test_send_event_still_refuses_a_private_target(self):
        """The guard the deleted path lacked, still in force on the live one."""
        from codeframe.core.notifications_config import (
            UnsafeWebhookHostError,
            vet_webhook_host,
        )

        with pytest.raises(UnsafeWebhookHostError):
            vet_webhook_host("169.254.169.254")

    def test_the_metadata_endpoint_is_the_named_case(self):
        """169.254.169.254 is the cloud-credential endpoint #656/#746 closed."""
        from codeframe.core.notifications_config import (
            UnsafeWebhookHostError,
            vet_webhook_host,
        )

        for host in ("127.0.0.1", "10.0.0.5", "169.254.169.254"):
            with pytest.raises(UnsafeWebhookHostError):
                vet_webhook_host(host)


class TestRoundTrippingTheMaskDoesNotDestroyTheUrl:
    """Masking creates a hazard: the UI loads the value into an editable field,
    so saving unchanged would persist the MASK and lose the real URL. Handled
    server-side so it protects any client, not just our own."""

    def test_the_put_handler_treats_the_mask_as_unchanged(self):
        from codeframe.ui.routers import settings_v2

        source = inspect.getsource(settings_v2.update_notification_settings)

        assert "redact_webhook_url(existing)" in source, (
            "a client echoing back the masked URL would overwrite the real one"
        )

    def test_a_genuinely_new_url_still_replaces_the_old(self):
        """The guard must only catch the mask, not block real edits."""
        old = SECRET_URL
        new = "https://hooks.example.com/services/NEW/TOKEN"

        assert new != redact_webhook_url(old), (
            "a real new URL must not be mistaken for the mask"
        )


class TestPutResponseIsMaskedToo:
    """Raised by the PR bot: masking only GET left the credential flowing out of
    the SAME handler's sibling response — and the PUT response is what the UI
    holds in state after a save, so the full URL sat in the browser until the
    next reload."""

    def test_the_put_handler_masks_its_response(self):
        from codeframe.ui.routers import settings_v2

        source = inspect.getsource(settings_v2.update_notification_settings)

        assert "redact_webhook_url(url)" in source
        assert "webhook_url=url," not in source, "the PUT response returns the raw URL"

    def test_the_put_response_sets_the_flag(self):
        from codeframe.ui.routers import settings_v2

        source = inspect.getsource(settings_v2.update_notification_settings)

        assert "webhook_url_set=bool(url)" in source, (
            "webhook_url_set was left at its False default after a successful save"
        )
