"""
Auto-Msg Scheduler — main.py
=============================
Reads "Pending" rows from a Google Sheet and sends the WhatsApp messages
via the Twilio API if their scheduled time is now or in the past.

Environment variables (set as GitHub Actions secrets):
  TWILIO_ACCOUNT_SID     — Your Twilio Account SID
  TWILIO_AUTH_TOKEN      — Your Twilio Auth Token
  TWILIO_WHATSAPP_NUMBER — Twilio sandbox/WhatsApp number, e.g. whatsapp:+14155238886
  GOOGLE_CREDENTIALS_JSON — Service-account JSON (single line, base64 or raw)
  SPREADSHEET_ID          — Google Sheet ID from its URL

Google Sheet columns (1-indexed):
  A (1): Phone Number     e.g. +919876543210
  B (2): Message          Plain text
  C (3): Scheduled Time   ISO format: 2025-07-04T14:30:00
  D (4): Status           "Pending" | "Sent" | "Failed"
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone

import gspread
from google.oauth2.service_account import Credentials
from twilio.rest import Client

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
logger = logging.getLogger(__name__)

# ── Column indices (0-based) ──────────────────────────────────────────────────
COL_PHONE  = 0
COL_MSG    = 1
COL_TIME   = 2
COL_STATUS = 3

PENDING_STATUS = "Pending"
SENT_STATUS    = "Sent"
FAILED_STATUS  = "Failed"

SHEET_NAME = os.environ.get("SHEET_NAME", "Messages")

GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _require_env(name: str) -> str:
    """Return env var or exit with a clear error."""
    value = os.environ.get(name, "").strip()
    if not value:
        logger.error("Required environment variable '%s' is not set.", name)
        sys.exit(1)
    return value


def _get_gspread_client() -> gspread.Client:
    """Build a gspread client from the service-account JSON stored in env."""
    creds_raw = _require_env("GOOGLE_CREDENTIALS_JSON")

    # Support both raw JSON string and base64-encoded JSON
    try:
        creds_dict = json.loads(creds_raw)
    except json.JSONDecodeError:
        import base64
        creds_dict = json.loads(base64.b64decode(creds_raw).decode("utf-8"))

    credentials = Credentials.from_service_account_info(creds_dict, scopes=GOOGLE_SCOPES)
    return gspread.authorize(credentials)


def _parse_scheduled_time(raw: str) -> datetime | None:
    """
    Parse an ISO-8601 datetime string.
    Accepts:
      - "2025-07-04T14:30" (no seconds, from <input type=datetime-local>)
      - "2025-07-04T14:30:00"
      - "2025-07-04T14:30:00Z" / "2025-07-04T14:30:00+05:30"
    Returns a timezone-aware UTC datetime, or None on failure.
    """
    if not raw:
        return None

    formats = [
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d %H:%M:%S",
    ]

    raw = raw.strip()

    # Try fromisoformat first (handles timezone offsets in Python ≥ 3.7)
    try:
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        pass

    for fmt in formats:
        try:
            dt = datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue

    logger.warning("Could not parse scheduled time: %r", raw)
    return None


def _send_whatsapp(twilio_client: Client, from_number: str, to_phone: str, body: str) -> str:
    """
    Send a WhatsApp message via Twilio.
    Returns the message SID on success, raises on error.
    """
    # Ensure 'whatsapp:' prefix
    to_whatsapp = to_phone if to_phone.startswith("whatsapp:") else f"whatsapp:{to_phone}"

    message = twilio_client.messages.create(
        from_=from_number,
        to=to_whatsapp,
        body=body,
    )
    return message.sid


# ── Main ──────────────────────────────────────────────────────────────────────

def run() -> None:
    # ── Load credentials & config ──────────────────────────────────────────
    twilio_sid    = _require_env("TWILIO_ACCOUNT_SID")
    twilio_token  = _require_env("TWILIO_AUTH_TOKEN")
    from_number   = _require_env("TWILIO_WHATSAPP_NUMBER")
    spreadsheet_id = _require_env("SPREADSHEET_ID")

    twilio_client = Client(twilio_sid, twilio_token)

    gc     = _get_gspread_client()
    sheet  = gc.open_by_key(spreadsheet_id).worksheet(SHEET_NAME)
    rows   = sheet.get_all_values()

    if not rows:
        logger.info("Sheet is empty. Nothing to do.")
        return

    # Skip header row if present
    header = rows[0]
    data_rows = rows[1:] if header and header[COL_STATUS].lower() == "status" else rows

    now_utc = datetime.now(timezone.utc)
    logger.info("Current UTC time: %s", now_utc.isoformat())

    processed = 0
    sent      = 0
    failed    = 0

    for row_index, row in enumerate(data_rows, start=2):  # 1-based, skip header
        # Pad short rows
        while len(row) < 4:
            row.append("")

        phone     = row[COL_PHONE].strip()
        message   = row[COL_MSG].strip()
        time_raw  = row[COL_TIME].strip()
        status    = row[COL_STATUS].strip()

        if status != PENDING_STATUS:
            continue

        if not phone or not message or not time_raw:
            logger.warning("Row %d: missing fields, skipping.", row_index)
            continue

        scheduled = _parse_scheduled_time(time_raw)
        if scheduled is None:
            logger.warning("Row %d: invalid scheduled time %r, skipping.", row_index, time_raw)
            continue

        if scheduled > now_utc:
            logger.info(
                "Row %d: scheduled for %s — not yet due.", row_index, scheduled.isoformat()
            )
            continue

        processed += 1
        logger.info("Row %d: sending to %s (scheduled %s)…", row_index, phone, scheduled.isoformat())

        try:
            sid = _send_whatsapp(twilio_client, from_number, phone, message)
            logger.info("Row %d: sent ✓  (SID: %s)", row_index, sid)
            sheet.update_cell(row_index, COL_STATUS + 1, SENT_STATUS)
            sent += 1
        except Exception as exc:
            logger.error("Row %d: failed to send — %s", row_index, exc)
            sheet.update_cell(row_index, COL_STATUS + 1, FAILED_STATUS)
            failed += 1

    logger.info(
        "Done. Processed: %d | Sent: %d | Failed: %d", processed, sent, failed
    )


if __name__ == "__main__":
    run()
