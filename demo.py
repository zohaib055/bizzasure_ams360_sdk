import json
import logging
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

ROOT_DIR = Path(__file__).resolve().parent
SDK_DIR = ROOT_DIR
sys.path.insert(0, str(SDK_DIR))

from ams360_sdk import AMS360Client, AMS360Settings
from ams360_sdk.errors import AMS360AuthError

LOGGER = logging.getLogger("ams360_demo")

DEMO_DIR = ROOT_DIR / "demos"
LOGS_JSON_PATH = ROOT_DIR / "logs.json"
SUCCESS_LOG_PATH = ROOT_DIR / "log.txt"
DEFAULT_DEMO_SCRIPTS = [
    "agency_info_get.py",
    "customer_get_list_by_name_prefix.py",
]


def _utc_now() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _find_assignment(text: str, name: str) -> Optional[str]:
    pattern = rf"^{name}\s*=\s*['\"]([^'\"]+)['\"]"
    match = re.search(pattern, text, flags=re.MULTILINE)
    return match.group(1) if match else None


def _read_demo_metadata(path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    return {
        "operation": _find_assignment(text, "OPERATION"),
        "method": _find_assignment(text, "METHOD"),
    }


def _order_demos(paths: list[Path]) -> list[Path]:
    # Run logout last to avoid invalidating the ticket early.
    logout = [path for path in paths if path.name == "logout.py"]
    others = [path for path in paths if path.name != "logout.py"]
    return others + logout


def _resolve_demo_paths(demo_dir: Path) -> tuple[list[Path], list[str]]:
    requested = os.getenv("AMS360_DEMO_SCRIPTS", "").strip()
    if not requested:
        requested = ",".join(DEFAULT_DEMO_SCRIPTS)

    missing: list[str] = []
    resolved: list[Path] = []
    for token in requested.split(","):
        name = token.strip()
        if not name:
            continue
        candidate = Path(name)
        if candidate.suffix.lower() != ".py":
            candidate = candidate.with_suffix(".py")
        if not candidate.is_absolute():
            if candidate.parent == Path("."):
                candidate = demo_dir / candidate.name
            else:
                candidate = ROOT_DIR / candidate
        if candidate.exists():
            resolved.append(candidate)
        else:
            missing.append(str(candidate))
    return _order_demos(resolved), missing


def _build_demo_env(base_env: dict, demo_path: Path) -> dict:
    env = base_env.copy()
    if demo_path.name == "customer_get_list_by_name_prefix.py":
        has_payload = bool(
            env.get("AMS360_DEMO_PAYLOAD_JSON")
            or env.get("AMS360_DEMO_PAYLOAD_FILE")
            or demo_path.with_suffix(".json").exists()
        )
        if not has_payload:
            name_prefix = env.get("AMS360_CUSTOMER_NAME_PREFIX", "A").strip()
            env["AMS360_DEMO_PAYLOAD_JSON"] = json.dumps({"NamePrefix": name_prefix})
            LOGGER.info(
                "Using default payload for %s (NamePrefix=%s).",
                demo_path.name,
                name_prefix,
            )
    return env


def _write_response(demo_path: Path, stdout_text: str) -> tuple[Optional[str], Optional[str]]:
    text = stdout_text.strip()
    if not text:
        return None, None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        response_path = demo_path.with_suffix(".response.txt")
        response_path.write_text(text, encoding="utf-8")
        return str(response_path), "text"
    response_path = demo_path.with_suffix(".response.json")
    response_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return str(response_path), "json"


def _write_stderr(demo_path: Path, stderr_text: str) -> Optional[str]:
    text = stderr_text.strip()
    if not text:
        return None
    stderr_path = demo_path.with_suffix(".stderr.log")
    stderr_path.write_text(text, encoding="utf-8")
    return str(stderr_path)


def _run_demo(demo_path: Path, env: dict) -> dict:
    metadata = _read_demo_metadata(demo_path)
    start_ts = datetime.utcnow()
    start_at = _utc_now()
    LOGGER.info("Running demo: %s", demo_path)
    result = subprocess.run(
        [sys.executable, str(demo_path)],
        env=env,
        capture_output=True,
        text=True,
    )
    duration = (datetime.utcnow() - start_ts).total_seconds()
    response_path, response_format = _write_response(demo_path, result.stdout)
    stderr_path = _write_stderr(demo_path, result.stderr)
    status = "success" if result.returncode == 0 else "failed"
    if status == "success":
        LOGGER.info("Demo succeeded: %s", demo_path.name)
    else:
        LOGGER.error("Demo failed: %s (exit %s)", demo_path.name, result.returncode)
    if response_path:
        LOGGER.info("Saved response: %s", response_path)
    if stderr_path:
        LOGGER.warning("Captured stderr: %s", stderr_path)
    return {
        "name": demo_path.stem,
        "path": str(demo_path),
        "operation": metadata.get("operation"),
        "method": metadata.get("method"),
        "status": status,
        "exit_code": result.returncode,
        "started_at": start_at,
        "duration_seconds": round(duration, 3),
        "response_path": response_path,
        "response_format": response_format,
        "stderr_path": stderr_path,
    }


def _write_logs_json(payload: dict) -> None:
    LOGS_JSON_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_success_log(payload: dict) -> None:
    summary = (
        "All demos completed successfully.\n"
        f"Started: {payload.get('started_at')}\n"
        f"Finished: {payload.get('finished_at')}\n"
        f"Total demos: {payload.get('total_demos')}\n"
    )
    SUCCESS_LOG_PATH.write_text(summary, encoding="utf-8")


def main() -> int:
    logging.basicConfig(
        level=os.getenv("AMS360_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(message)s",
    )

    run_started_at = _utc_now()
    if not DEMO_DIR.exists():
        LOGGER.error("Missing demos directory: %s", DEMO_DIR)
        _write_logs_json(
            {
                "started_at": run_started_at,
                "finished_at": _utc_now(),
                "all_succeeded": False,
                "total_demos": 0,
                "error": f"Missing demos directory: {DEMO_DIR}",
                "demos": [],
            }
        )
        return 1

    # Optional: set credentials here if you don't want to use env vars.
    agency_no = "8880006-1"
    login_id = "testuser"
    password = "wK1atfrjjY7"
    employee_code = ""
    ticket_override = ""

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
        error = (
            "Missing credentials. Set AMS360_AGENCY_NO, AMS360_LOGIN_ID, "
            "AMS360_PASSWORD or AMS360_TICKET (or fill the placeholders in demo.py)."
        )
        LOGGER.error(error)
        _write_logs_json(
            {
                "started_at": run_started_at,
                "finished_at": _utc_now(),
                "all_succeeded": False,
                "total_demos": 0,
                "error": error,
                "demos": [],
            }
        )
        return 1

    try:
        LOGGER.info("Logging in to AMS360")
        client = AMS360Client.from_settings(settings=settings, auto_login=True)
        ticket = client.ensure_ticket()
        LOGGER.info("Login succeeded; ticket received")
    except (FileNotFoundError, AMS360AuthError) as exc:
        error = f"Login failed: {exc}"
        LOGGER.error(error)
        _write_logs_json(
            {
                "started_at": run_started_at,
                "finished_at": _utc_now(),
                "all_succeeded": False,
                "total_demos": 0,
                "error": error,
                "demos": [],
            }
        )
        return 1

    env = os.environ.copy()
    env["AMS360_TICKET"] = ticket

    # Optional: override default demos with AMS360_DEMO_SCRIPTS (comma-separated).
    demo_paths, missing = _resolve_demo_paths(DEMO_DIR)
    if not demo_paths and not missing:
        error = "No demo scripts found to run."
        LOGGER.error(error)
        _write_logs_json(
            {
                "started_at": run_started_at,
                "finished_at": _utc_now(),
                "all_succeeded": False,
                "total_demos": 0,
                "error": error,
                "demos": [],
            }
        )
        return 1

    LOGGER.info("Demo count: %s (missing: %s)", len(demo_paths), len(missing))
    results: list[dict] = []
    all_succeeded = True

    for missing_path in missing:
        results.append(
            {
                "name": Path(missing_path).stem,
                "path": missing_path,
                "operation": None,
                "method": None,
                "status": "missing",
                "exit_code": None,
                "started_at": None,
                "duration_seconds": None,
                "response_path": None,
                "response_format": None,
                "stderr_path": None,
            }
        )
        all_succeeded = False

    # Run each demo and capture its output to per-demo response files.
    for demo_path in demo_paths:
        if not demo_path.exists():
            LOGGER.error("Demo script not found: %s", demo_path)
            results.append(
                {
                    "name": demo_path.stem,
                    "path": str(demo_path),
                    "operation": None,
                    "method": None,
                    "status": "missing",
                    "exit_code": None,
                    "started_at": None,
                    "duration_seconds": None,
                    "response_path": None,
                    "response_format": None,
                    "stderr_path": None,
                }
            )
            all_succeeded = False
            continue
        demo_env = _build_demo_env(env, demo_path)
        entry = _run_demo(demo_path, demo_env)
        results.append(entry)
        if entry["status"] != "success":
            all_succeeded = False

    run_finished_at = _utc_now()
    payload = {
        "started_at": run_started_at,
        "finished_at": run_finished_at,
        "all_succeeded": all_succeeded,
        "total_demos": len(demo_paths) + len(missing),
        "demos": results,
    }
    _write_logs_json(payload)

    if all_succeeded and demo_paths:
        _write_success_log(payload)
        LOGGER.info("Success log written: %s", SUCCESS_LOG_PATH)
    else:
        LOGGER.info("One or more demos failed; success log not written.")

    return 0 if all_succeeded else 1


if __name__ == "__main__":
    raise SystemExit(main())
