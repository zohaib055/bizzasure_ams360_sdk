import argparse
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

from ams360_sdk import AMS360Client, AMS360Settings, Generated, models
from ams360_sdk.errors import AMS360AuthError, AMS360SoapError

DEMO_PAYLOAD_PATH = ROOT_DIR / "demos" / "customer_get_by_id.json"
FIELD_NAMES = ["CustomerId"]
LOG_PATH = ROOT_DIR / "log.txt"
CUSTOMER_ID_OVERRIDE = None

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


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON in {path}: {exc}") from exc


def _load_payload() -> dict:
    if CUSTOMER_ID_OVERRIDE:
        return {"CustomerId": CUSTOMER_ID_OVERRIDE}

    env_customer_id = os.getenv("AMS360_CUSTOMER_ID", "").strip()
    if env_customer_id:
        return {"CustomerId": env_customer_id}

    env_json = os.getenv("AMS360_DEMO_PAYLOAD_JSON", "")
    if env_json:
        try:
            return json.loads(env_json)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Invalid AMS360_DEMO_PAYLOAD_JSON: {exc}") from exc

    payload_file = os.getenv("AMS360_DEMO_PAYLOAD_FILE", "")
    if payload_file:
        return _load_json(Path(payload_file))

    if DEMO_PAYLOAD_PATH.exists():
        return _load_json(DEMO_PAYLOAD_PATH)

    return {}


def _json_default(value: object) -> object:
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return str(value)


class TestCustomerGetById(unittest.TestCase):
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

    def test_customer_get_by_id(self) -> None:
        payload = _load_payload()
        if not payload:
            fields = ", ".join(FIELD_NAMES)
            raise unittest.SkipTest(
                "Missing payload JSON. Provide AMS360_DEMO_PAYLOAD_JSON, "
                f"AMS360_DEMO_PAYLOAD_FILE, or create {DEMO_PAYLOAD_PATH} "
                f"with fields: {fields}."
            )
        if "CustomerId" not in payload:
            self.fail("CustomerId is required in the payload.")

        client = self._get_client()
        gen = Generated(client)
        request = models.CustomerGetByIdRequest(**payload)
        try:
            result = gen.customer_get_by_id_json(request=request)
        except AMS360SoapError as exc:
            LOGGER.error("SOAP error: %s", exc)
            self.skipTest(f"AMS360 SOAP error: {exc}")

        self.assertIsInstance(result, dict)
        print(json.dumps(result, indent=2, default=_json_default))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--customer-id", dest="customer_id", default=None)
    args, remaining = parser.parse_known_args()
    if args.customer_id:
        CUSTOMER_ID_OVERRIDE = args.customer_id.strip()
    unittest.main(argv=[sys.argv[0], *remaining])
