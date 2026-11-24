"""Submit a US daily workflow request from the VPS timer."""

import argparse
import base64
import json
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

REPOSITORY = "EFSing/us_watchlist"
API = "https://api.github.com"
WORKFLOW = f"{API}/repos/{REPOSITORY}/actions/workflows/iwb-daily.yml"


def _github_json(url: str, token: str, operation: str, payload: dict | None = None) -> dict:
    body = json.dumps(payload).encode() if payload is not None else None
    request = Request(url, data=body, headers={
        "Accept": "application/vnd.github+json", "Content-Type": "application/json",
        "User-Agent": "us-iwb-vps-dispatcher",
        "X-GitHub-Api-Version": "2026-03-10",
    })
    request.add_unredirected_header("Authorization", f"Bearer {token}")
    try:
        with urlopen(request, timeout=20) as response:
            result = json.loads(response.read(32768))
    except HTTPError as error:
        raise ValueError(f"{operation}_HTTP_{error.code}") from None
    except (OSError, ValueError) as error:
        raise ValueError(f"{operation}_UNCONFIRMED {type(error).__name__}") from None
    if not isinstance(result, dict):
        raise ValueError(f"{operation}_UNCONFIRMED INVALID_RESPONSE")
    return result


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _app_jwt(key: Path, app_id: str, now: datetime) -> str:
    header = _base64url(b'{"alg":"RS256","typ":"JWT"}')
    issued_at = int(now.timestamp())
    claims = {"iss": app_id, "iat": issued_at - 60, "exp": issued_at + 180}
    message = f"{header}.{_base64url(json.dumps(claims).encode())}"
    try:
        signature = subprocess.run(
            ["/usr/bin/openssl", "dgst", "-sha256", "-sign", str(key)],
            input=message.encode(),
            capture_output=True,
            check=True,
            timeout=5,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        raise ValueError("IWB_VPS_GITHUB_APP_SIGNING_FAILED") from None
    return f"{message}.{_base64url(signature)}"


def installation_token(key: Path, app_id: str, installation_id: str, now: datetime) -> str:
    if not all(re.fullmatch(r"[1-9][0-9]*", value) for value in (app_id, installation_id)):
        raise ValueError("IWB_VPS_INVALID_GITHUB_APP_IDS")
    result = _github_json(
        f"{API}/app/installations/{installation_id}/access_tokens",
        _app_jwt(key, app_id, now),
        "IWB_VPS_INSTALLATION_TOKEN",
        {"repositories": ["us_watchlist"], "permissions": {"actions": "write"}},
    )
    token = result.get("token")
    if not isinstance(token, str) or not token or any(character.isspace() for character in token):
        raise ValueError("IWB_VPS_INVALID_INSTALLATION_TOKEN")
    return token


def dispatch(token: str, trade_date: str) -> int:
    result = _github_json(
        f"{WORKFLOW}/dispatches", token, "IWB_VPS_DISPATCH",
        {"ref": "main", "inputs": {"vps_trade_date": trade_date}},
    )
    run_id = result.get("workflow_run_id")
    if type(run_id) is not int or run_id <= 0:
        raise ValueError("IWB_VPS_DISPATCH_UNCONFIRMED INVALID_RUN_ID")
    return run_id


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Verify GitHub access without dispatching.")
    options = parser.parse_args(argv)
    now = datetime.now(ZoneInfo("America/New_York"))
    trade_date = now.date().isoformat()
    try:
        key = Path(os.environ["CREDENTIALS_DIRECTORY"]) / "github-app-key"
        token = installation_token(
            key, os.environ["IWB_GITHUB_APP_ID"], os.environ["IWB_GITHUB_INSTALLATION_ID"], now,
        )
        if options.check:
            workflow = _github_json(WORKFLOW, token, "IWB_VPS_WORKFLOW_CHECK")
            if workflow.get("state") != "active":
                raise ValueError("IWB_VPS_WORKFLOW_NOT_ACTIVE")
            print("IWB_VPS_GITHUB_APP_AUTH_OK")
            return
        run_id = dispatch(token, trade_date)
    except KeyError:
        raise SystemExit("IWB_VPS_GITHUB_APP_CONFIGURATION_REQUIRED") from None
    except ValueError as error:
        raise SystemExit(f"{trade_date} {error}") from None
    print(f"IWB_VPS_DISPATCHED {trade_date} https://github.com/{REPOSITORY}/actions/runs/{run_id}")


if __name__ == "__main__":
    main()
