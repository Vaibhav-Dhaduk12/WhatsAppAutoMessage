"""
Tests for main.py — Auto-Msg Scheduler
Run with:  python -m pytest tests/test_main.py -v
"""

import json
import sys
import os
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch, call

import pytest

# ── Ensure project root is on sys.path ──────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import (
    _parse_scheduled_time,
    _send_whatsapp,
    PENDING_STATUS,
    SENT_STATUS,
    FAILED_STATUS,
    COL_PHONE,
    COL_MSG,
    COL_TIME,
    COL_STATUS,
)


# ── _parse_scheduled_time ────────────────────────────────────────────────────

class TestParseScheduledTime:
    def test_iso_with_seconds(self):
        dt = _parse_scheduled_time("2025-07-04T14:30:00")
        assert dt == datetime(2025, 7, 4, 14, 30, 0, tzinfo=timezone.utc)

    def test_iso_without_seconds(self):
        dt = _parse_scheduled_time("2025-07-04T14:30")
        assert dt == datetime(2025, 7, 4, 14, 30, tzinfo=timezone.utc)

    def test_iso_with_z(self):
        dt = _parse_scheduled_time("2025-07-04T14:30:00Z")
        assert dt is not None
        assert dt.tzinfo is not None
        assert dt == datetime(2025, 7, 4, 14, 30, 0, tzinfo=timezone.utc)

    def test_iso_with_offset(self):
        # +05:30 → UTC = 14:30 - 5:30 = 09:00
        dt = _parse_scheduled_time("2025-07-04T14:30:00+05:30")
        assert dt is not None
        assert dt.hour == 9
        assert dt.minute == 0

    def test_space_separated(self):
        dt = _parse_scheduled_time("2025-07-04 14:30:00")
        assert dt == datetime(2025, 7, 4, 14, 30, 0, tzinfo=timezone.utc)

    def test_space_no_seconds(self):
        dt = _parse_scheduled_time("2025-07-04 14:30")
        assert dt == datetime(2025, 7, 4, 14, 30, tzinfo=timezone.utc)

    def test_empty_string(self):
        assert _parse_scheduled_time("") is None

    def test_none_value(self):
        assert _parse_scheduled_time(None) is None

    def test_invalid_string(self):
        assert _parse_scheduled_time("not-a-date") is None

    def test_whitespace_stripped(self):
        dt = _parse_scheduled_time("  2025-07-04T14:30:00  ")
        assert dt == datetime(2025, 7, 4, 14, 30, 0, tzinfo=timezone.utc)


# ── _send_whatsapp ───────────────────────────────────────────────────────────

class TestSendWhatsapp:
    def _make_client(self, sid="SM123"):
        mock_msg = MagicMock()
        mock_msg.sid = sid

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_msg
        return mock_client

    def test_adds_whatsapp_prefix(self):
        client = self._make_client()
        _send_whatsapp(client, "whatsapp:+14155238886", "+919876543210", "Hello")
        _, kwargs = client.messages.create.call_args
        assert kwargs["to"] == "whatsapp:+919876543210"

    def test_preserves_existing_prefix(self):
        client = self._make_client()
        _send_whatsapp(client, "whatsapp:+14155238886", "whatsapp:+919876543210", "Hi")
        _, kwargs = client.messages.create.call_args
        assert kwargs["to"] == "whatsapp:+919876543210"

    def test_returns_sid(self):
        client = self._make_client(sid="SMABCDEF")
        result = _send_whatsapp(client, "whatsapp:+14155238886", "+1234567890", "Test")
        assert result == "SMABCDEF"

    def test_passes_from_and_body(self):
        client = self._make_client()
        _send_whatsapp(client, "whatsapp:+14155238886", "+1234567890", "My message")
        _, kwargs = client.messages.create.call_args
        assert kwargs["from_"] == "whatsapp:+14155238886"
        assert kwargs["body"] == "My message"

    def test_raises_on_twilio_error(self):
        client = MagicMock()
        client.messages.create.side_effect = Exception("Twilio error")
        with pytest.raises(Exception, match="Twilio error"):
            _send_whatsapp(client, "whatsapp:+14155238886", "+1234567890", "msg")


# ── run() integration-style tests ───────────────────────────────────────────

class TestRun:
    """Tests for the run() function using heavy mocking."""

    BASE_ENV = {
        "TWILIO_ACCOUNT_SID":      "ACtest",
        "TWILIO_AUTH_TOKEN":       "token",
        "TWILIO_WHATSAPP_NUMBER":  "whatsapp:+14155238886",
        # Intentionally invalid/non-functional key — used only to test JSON parsing logic.
        "GOOGLE_CREDENTIALS_JSON": json.dumps({
            "type": "service_account",
            "project_id": "test",
            "private_key_id": "key_id",
            "private_key": "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA\n-----END RSA PRIVATE KEY-----\n",
            "client_email": "test@test.iam.gserviceaccount.com",
            "client_id": "123",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }),
        "SPREADSHEET_ID": "sheet123",
    }

    def _past_time(self, minutes=30):
        dt = datetime.now(timezone.utc) - timedelta(minutes=minutes)
        return dt.strftime("%Y-%m-%dT%H:%M:%S")

    def _future_time(self, minutes=30):
        dt = datetime.now(timezone.utc) + timedelta(minutes=minutes)
        return dt.strftime("%Y-%m-%dT%H:%M:%S")

    def _make_sheet_mock(self, rows):
        sheet = MagicMock()
        sheet.get_all_values.return_value = rows
        return sheet

    def _make_gc_mock(self, sheet):
        gc = MagicMock()
        gc.open_by_key.return_value.worksheet.return_value = sheet
        return gc

    @patch("main.Client")
    @patch("main._get_gspread_client")
    def test_sends_pending_past_due(self, mock_gc_fn, mock_twilio_cls, monkeypatch):
        for k, v in self.BASE_ENV.items():
            monkeypatch.setenv(k, v)

        past = self._past_time()
        rows = [
            ["Phone Number", "Message", "Scheduled Time", "Status"],
            ["+919876543210", "Hello!", past, "Pending"],
        ]
        sheet = self._make_sheet_mock(rows)
        mock_gc_fn.return_value = self._make_gc_mock(sheet)

        mock_msg = MagicMock(); mock_msg.sid = "SM001"
        mock_twilio_cls.return_value.messages.create.return_value = mock_msg

        from main import run
        run()

        mock_twilio_cls.return_value.messages.create.assert_called_once()
        sheet.update_cell.assert_called_once_with(2, COL_STATUS + 1, SENT_STATUS)

    @patch("main.Client")
    @patch("main._get_gspread_client")
    def test_skips_future_message(self, mock_gc_fn, mock_twilio_cls, monkeypatch):
        for k, v in self.BASE_ENV.items():
            monkeypatch.setenv(k, v)

        future = self._future_time()
        rows = [
            ["Phone Number", "Message", "Scheduled Time", "Status"],
            ["+919876543210", "Hello!", future, "Pending"],
        ]
        sheet = self._make_sheet_mock(rows)
        mock_gc_fn.return_value = self._make_gc_mock(sheet)

        from main import run
        run()

        mock_twilio_cls.return_value.messages.create.assert_not_called()
        sheet.update_cell.assert_not_called()

    @patch("main.Client")
    @patch("main._get_gspread_client")
    def test_skips_already_sent(self, mock_gc_fn, mock_twilio_cls, monkeypatch):
        for k, v in self.BASE_ENV.items():
            monkeypatch.setenv(k, v)

        past = self._past_time()
        rows = [
            ["Phone Number", "Message", "Scheduled Time", "Status"],
            ["+919876543210", "Hello!", past, "Sent"],
        ]
        sheet = self._make_sheet_mock(rows)
        mock_gc_fn.return_value = self._make_gc_mock(sheet)

        from main import run
        run()

        mock_twilio_cls.return_value.messages.create.assert_not_called()

    @patch("main.Client")
    @patch("main._get_gspread_client")
    def test_marks_failed_on_twilio_error(self, mock_gc_fn, mock_twilio_cls, monkeypatch):
        for k, v in self.BASE_ENV.items():
            monkeypatch.setenv(k, v)

        past = self._past_time()
        rows = [
            ["Phone Number", "Message", "Scheduled Time", "Status"],
            ["+919876543210", "Hello!", past, "Pending"],
        ]
        sheet = self._make_sheet_mock(rows)
        mock_gc_fn.return_value = self._make_gc_mock(sheet)

        mock_twilio_cls.return_value.messages.create.side_effect = Exception("Network error")

        from main import run
        run()

        sheet.update_cell.assert_called_once_with(2, COL_STATUS + 1, FAILED_STATUS)

    @patch("main.Client")
    @patch("main._get_gspread_client")
    def test_empty_sheet(self, mock_gc_fn, mock_twilio_cls, monkeypatch):
        for k, v in self.BASE_ENV.items():
            monkeypatch.setenv(k, v)

        sheet = self._make_sheet_mock([])
        mock_gc_fn.return_value = self._make_gc_mock(sheet)

        from main import run
        run()  # Should not raise

        mock_twilio_cls.return_value.messages.create.assert_not_called()

    @patch("main.Client")
    @patch("main._get_gspread_client")
    def test_multiple_rows_mixed(self, mock_gc_fn, mock_twilio_cls, monkeypatch):
        """Two pending rows (one past, one future) + one already sent."""
        for k, v in self.BASE_ENV.items():
            monkeypatch.setenv(k, v)

        past   = self._past_time()
        future = self._future_time()
        rows = [
            ["Phone Number", "Message", "Scheduled Time", "Status"],
            ["+911111111111", "Past msg",   past,   "Pending"],
            ["+912222222222", "Future msg", future, "Pending"],
            ["+913333333333", "Old msg",    past,   "Sent"],
        ]
        sheet = self._make_sheet_mock(rows)
        mock_gc_fn.return_value = self._make_gc_mock(sheet)

        mock_msg = MagicMock(); mock_msg.sid = "SM999"
        mock_twilio_cls.return_value.messages.create.return_value = mock_msg

        from main import run
        run()

        # Only the first row (past+pending) should be sent
        assert mock_twilio_cls.return_value.messages.create.call_count == 1
        sheet.update_cell.assert_called_once_with(2, COL_STATUS + 1, SENT_STATUS)
