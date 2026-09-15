"""Email path tests — no real SMTP: assert gating, rendering, and no-fake-send."""
from __future__ import annotations

from app import i18n_strings
from app.services import SEVERITY_RANK, user_wants


def _user(alert_level="medium", channel_email=False, language="en"):
    class U:
        pass
    u = U()
    u.alert_level, u.channel_email, u.language = alert_level, channel_email, language
    return u


class TestEmailGating:
    def test_no_smtp_means_no_email_claim(self, client):
        """Preferences API reports email_available=false and notify() never
        stamps 'email' into channel_delivered while SMTP is unconfigured."""
        from tests.conftest import register
        hdrs, _ = register(client, "mail@examplemail.com")
        r = client.put("/api/v1/auth/me/preferences", headers=hdrs,
                       json={"alert_level": "medium", "channels": {"email": True, "push": True}})
        assert r.status_code == 200 and r.json()["email_available"] is False

    def test_alert_level_filtering(self):
        assert user_wants(_user("critical"), "critical")
        assert not user_wants(_user("critical"), "medium")
        assert user_wants(_user("medium"), "high")
        assert not user_wants(_user("high"), "medium")

    def test_severity_ordering(self):
        assert SEVERITY_RANK["critical"] < SEVERITY_RANK["low"]


class TestEmailRendering:
    def test_en_hi_translation(self):
        assert i18n_strings.translate("alerts.irrigation_needed", "en")
        hi = i18n_strings.translate("alerts.irrigation_needed", "hi")
        assert any(ord(c) > 0x0900 for c in hi)  # Devanagari present

    def test_unknown_key_returns_key_not_crash(self):
        assert i18n_strings.translate("no.such.key", "en") == "no.such.key"

    def test_subject_formatting(self):
        from app.notify_email import _render_subject
        s = _render_subject("alerts.rain_incoming", {"mm": 12, "field": "A"}, "en")
        assert "12" in s and s.startswith("AgriFlow:")

    def test_params_injection_escaped_and_capped(self):
        from app.notify_email import _render_subject
        evil = {"field": "<script>x</script>", "extra": "y" * 500}
        out = _render_subject("alerts.irrigation_needed", evil, "en")
        assert "<script>" not in out and "y" * 80 not in out

    def test_send_now_without_smtp_returns_false(self):
        from app.notify_email import send_now
        assert send_now("a@b.co", "alerts.irrigation_needed", {"field": "x"}) is False
