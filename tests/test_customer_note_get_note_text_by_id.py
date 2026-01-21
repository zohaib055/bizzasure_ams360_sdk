import json
import logging
import os
import sys
import unittest
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from ams360_sdk import AMS360Client, AMS360Settings, Generated
from ams360_sdk.errors import AMS360AuthError, AMS360SoapError

METHOD = 'customer_note_get_note_text_by_id'
LOG_PATH = ROOT_DIR / "log.txt"

LOGGER = logging.getLogger("ams360_test")


def _configure_logging() -> None:
    if LOGGER.handlers:
        return
    LOGGER.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    file_handler = logging.FileHandler(LOG_PATH, mode="a", encoding="utf-8")
    file_handler.setFormatter(formatter)
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    LOGGER.addHandler(file_handler)
    LOGGER.addHandler(stream_handler)

def _json_default(value: object) -> object:
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return str(value)


class TestCustomerNoteGetNoteTextById(unittest.TestCase):
    def _get_client(self) -> AMS360Client:
        _configure_logging()
        # Optional: set credentials here if you don't want to use env vars.
        agency_no = os.getenv("AMS360_AGENCY_NO") or "8880006-1"
        login_id = os.getenv("AMS360_LOGIN_ID") or "testuser"
        password = os.getenv("AMS360_PASSWORD") or "wK1atfrjjY7"
        employee_code = os.getenv("AMS360_EMPLOYEE_CODE") or ""
        ticket_override = os.getenv("AMS360_TICKET") or ""

        settings = AMS360Settings.from_env()
        if agency_no:
            settings.agency_no = agency_no
        if login_id:
            settings.login_id = login_id
        if password:
            settings.password = password
        if employee_code:
            settings.employee_code = employee_code
        if ticket_override:
            settings.ticket = ticket_override

        if not settings.ticket and not settings.has_credentials():
            raise unittest.SkipTest(
                "Missing credentials. Set AMS360_AGENCY_NO, AMS360_LOGIN_ID, "
                "AMS360_PASSWORD or AMS360_TICKET."
            )

        try:
            client = AMS360Client.from_settings(settings=settings, auto_login=True)
            ticket = client.ensure_ticket()
            LOGGER.info("Ticket generated: %s", ticket)
        except AMS360AuthError as exc:
            self.fail(f"Login failed: {exc}")
        return client

    def test_customer_note_get_note_text_by_id(self) -> None:
        client = self._get_client()
        gen = Generated(client)

        try:
            result = getattr(gen, f"{METHOD}_json")()
        except AMS360SoapError as exc:
            LOGGER.error("SOAP error: %s", exc)
            self.skipTest(f"AMS360 SOAP error: {exc}")

        self.assertIsInstance(result, dict)
        print(json.dumps(result, indent=2, default=_json_default))


if __name__ == "__main__":
    unittest.main()
