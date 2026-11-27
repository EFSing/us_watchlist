"""Read and verify private GitHub Actions artifacts for the US daily workflow."""

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from time import sleep
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from zipfile import BadZipFile, ZipFile

from us_watchlist.domain.models import require_utc
from us_watchlist.integrations.local_artifacts import publish_once

MAX_ARTIFACT_BYTES = 32 * 1024 * 1024


@dataclass(frozen=True)
class Artifact:
    name: str
    artifact_id: int
    digest: str
    run_id: int
    created_at: datetime | None = None


class GitHubArtifacts:
    def __init__(self):
        self.repo = os.environ["GITHUB_REPOSITORY"]
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", self.repo):
            raise ValueError("GITHUB_INVALID_REPOSITORY")
        self.token = os.environ["GH_TOKEN"]
        self.branch = os.environ["IWB_DEFAULT_BRANCH"]
        self.actions_root = f"https://api.github.com/repos/{self.repo}/actions"
        self.root = f"{self.actions_root}/artifacts"

    def _read(self, url: str) -> bytes:
        request = Request(url, headers={
            "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
        })
        # The archive URL redirects to a signed storage URL. Keep credentials at api.github.com.
        request.add_unredirected_header("Authorization", f"Bearer {self.token}")
        download = url.endswith("/zip")
        transient_codes = {429, 500, 502, 503, 504}
        if download:
            # Newly finalized uploads can surface in the REST download endpoint after a short delay.
            transient_codes.add(404)
        for delay in ((2, 6, None) if download else (3, None)):
            try:
                with urlopen(request, timeout=25) as response:
                    payload = response.read(MAX_ARTIFACT_BYTES + 1)
                if len(payload) > MAX_ARTIFACT_BYTES:
                    raise ValueError("GITHUB_ARTIFACT_TOO_LARGE")
                return payload
            except HTTPError as error:
                if delay is None or error.code not in transient_codes:
                    endpoint = "API" if urlsplit(error.geturl()).hostname == "api.github.com" else "STORAGE"
                    raise ValueError(f"GITHUB_ARTIFACT_{endpoint}_HTTP_{error.code}") from None
            except (URLError, TimeoutError, OSError) as error:
                if delay is None:
                    raise ValueError(f"GITHUB_ARTIFACT_NETWORK_{type(error).__name__}") from None
            sleep(delay)
        raise AssertionError("GitHub request exhausted its retry loop")

    def schedule_created_at(self, code_sha: str, *, event: str = "schedule") -> datetime:
        run_id = int(os.environ["GITHUB_RUN_ID"])
        if run_id <= 0:
            raise ValueError("GITHUB_INVALID_RUN_ID")
        run = json.loads(self._read(f"{self.actions_root}/runs/{run_id}"))
        if (run["id"], run["event"], run["head_branch"], run["head_sha"]) != (
            run_id, event, self.branch, code_sha,
        ):
            raise ValueError("GITHUB_SCHEDULE_RUN_MISMATCH")
        created = datetime.fromisoformat(run["created_at"])
        require_utc(created)
        return created

    def catalog(self) -> dict[str, Artifact]:
        selected = {}
        for page in range(1, 21):
            rows = json.loads(self._read(f"{self.root}?per_page=100&page={page}"))["artifacts"]
            for row in rows:
                name = row["name"]
                run = row.get("workflow_run") or {}
                if (row["expired"] or not re.fullmatch(r"us-iwb-v1-(?:pool|daily|paper)-\d{4}-\d{2}-\d{2}", name)
                    or run.get("head_branch") != self.branch or run.get("repository_id") != run.get("head_repository_id")):
                    continue
                if name in selected:
                    raise ValueError(f"GITHUB_ARTIFACT_IDENTITY_CONFLICT {name}")
                created_at = datetime.fromisoformat(row["created_at"]) if row.get("created_at") else None
                selected[name] = Artifact(name, row["id"], row.get("digest") or "", run["id"], created_at)
            if len(rows) < 100:
                return selected
        raise ValueError("GITHUB_ARTIFACT_CATALOG_PAGE_LIMIT")

    def restore(self, artifact: Artifact, output: Path, names: set[str]) -> None:
        self._restore(artifact, output, lambda entries: entries == names)

    def restore_paper_bundle(self, artifact: Artifact, output: Path) -> None:
        fixed = {"study.json", "paper-receipt.json", "combined-report.html", "paper-summary.txt"}

        def valid_names(entries: set[str]) -> bool:
            days = entries - fixed
            return fixed <= entries and bool(days) and all(
                re.fullmatch(r"days/[0-9]{4}-[0-9]{2}-[0-9]{2}\.json", name) for name in days
            )

        self._restore(artifact, output, valid_names)

    def _restore(self, artifact: Artifact, output: Path, valid_names) -> None:
        body = self._read(f"{self.root}/{artifact.artifact_id}/zip")
        if artifact.digest != f"sha256:{sha256(body).hexdigest()}":
            raise ValueError(f"GITHUB_ARTIFACT_DIGEST_MISMATCH {artifact.name}")
        try:
            with ZipFile(BytesIO(body)) as archive:
                entries = archive.infolist()
                names = set(archive.namelist())
                if (len(entries) != len(names) or not valid_names(names)
                    or any(entry.orig_filename != entry.filename or entry.flag_bits & 1 for entry in entries)
                    or sum(entry.file_size for entry in entries) > MAX_ARTIFACT_BYTES):
                    raise ValueError(f"GITHUB_ARTIFACT_UNEXPECTED_ENTRIES {artifact.name}")
                payloads = {entry.filename: archive.read(entry) for entry in entries}
        except (BadZipFile, RuntimeError) as error:
            raise ValueError(f"GITHUB_ARTIFACT_INVALID_ZIP {artifact.name}") from error
        for name, payload in payloads.items():
            publish_once(output / name, payload)


def paper_workflow_variables() -> tuple[bool, str | None]:
    return os.environ.get("US_IWB_PAPER_ENABLED") == "true", os.environ.get("US_IWB_PAPER_START_DATE")


def write_workflow_outputs(outputs: dict[str, str]) -> None:
    path = Path(os.environ["GITHUB_OUTPUT"])
    with path.open("a", encoding="utf-8") as output:
        for key, value in outputs.items():
            if "\n" in value or "\r" in value:
                raise ValueError("UNSAFE_GITHUB_OUTPUT")
            output.write(f"{key}={value}\n")
