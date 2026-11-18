"""Publish a complete immutable artifact on the local filesystem."""

from os import link
from pathlib import Path
from tempfile import NamedTemporaryFile


def publish_once(path: Path, body: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = NamedTemporaryFile(
        mode="wb", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False
    )
    temporary = Path(staging.name)
    try:
        with staging:
            staging.write(body)
        try:
            link(temporary, path)
        except FileExistsError:
            if path.read_bytes() != body:
                raise ValueError(f"Artifact identity already used with different content: {path}")
    finally:
        temporary.unlink(missing_ok=True)
