"""Submit a US daily workflow request from the VPS timer."""

import json
import os
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

REPOSITORY = "EFSing/us_watchlist"
WORKFLOW = f"https://api.github.com/repos/{REPOSITORY}/actions/workflows/iwb-daily.yml"


def dispatch(token: str, trade_date: str) -> int:
    body = json.dumps({"ref": "main", "inputs": {"vps_trade_date": trade_date}}).encode()
    request = Request(f"{WORKFLOW}/dispatches", data=body, method="POST", headers={
        "Accept": "application/vnd.github+json", "Content-Type": "application/json",
        "X-GitHub-Api-Version": "2026-03-10",
    })
    request.add_unredirected_header("Authorization", f"Bearer {token}")
    try:
        with urlopen(request, timeout=20) as response:
            run_id = json.loads(response.read(4096))["workflow_run_id"]
    except HTTPError as error:
        raise ValueError(f"IWB_VPS_DISPATCH_HTTP_{error.code}") from None
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise ValueError(f"IWB_VPS_DISPATCH_UNCONFIRMED {type(error).__name__}") from None
    if type(run_id) is not int or run_id <= 0:
        raise ValueError("IWB_VPS_DISPATCH_UNCONFIRMED INVALID_RUN_ID")
    return run_id


def main() -> None:
    credential = Path(os.environ["CREDENTIALS_DIRECTORY"]) / "github-token"
    token = credential.read_text(encoding="utf-8").strip()
    if not token or any(character.isspace() for character in token):
        raise SystemExit("IWB_VPS_INVALID_GITHUB_TOKEN")
    trade_date = datetime.now(ZoneInfo("America/New_York")).date().isoformat()
    try:
        run_id = dispatch(token, trade_date)
    except ValueError as error:
        raise SystemExit(f"{trade_date} {error}") from None
    print(f"IWB_VPS_DISPATCHED {trade_date} https://github.com/{REPOSITORY}/actions/runs/{run_id}")


if __name__ == "__main__":
    main()
