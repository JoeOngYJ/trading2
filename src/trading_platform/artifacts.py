from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path

from .contracts import ArtifactRef


class ArtifactStore:
    """Content-addressed immutable artifact storage on a durable volume."""

    def __init__(self, root: Path):
        self.root = root

    def put(self, content: bytes, media_type: str) -> ArtifactRef:
        hex_digest = hashlib.sha256(content).hexdigest()
        relative = Path("sha256") / hex_digest[:2] / hex_digest[2:4] / hex_digest
        target = self.root / relative
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o750)
        if target.exists():
            if target.read_bytes() != content:
                raise RuntimeError("artifact digest collision or corrupt existing artifact")
        else:
            fd, temporary_name = tempfile.mkstemp(prefix=f".{hex_digest}.", dir=target.parent)
            try:
                with os.fdopen(fd, "wb") as handle:
                    handle.write(content)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.chmod(temporary_name, 0o440)
                os.replace(temporary_name, target)
                directory_fd = os.open(target.parent, os.O_DIRECTORY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
            except BaseException:
                try:
                    os.unlink(temporary_name)
                except FileNotFoundError:
                    pass
                raise
        return ArtifactRef(
            digest=f"sha256:{hex_digest}",
            media_type=media_type,
            byte_length=len(content),
            storage_path=str(relative),
        )

    def read(self, artifact: ArtifactRef) -> bytes:
        relative = Path(artifact.storage_path)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("artifact storage path escapes the artifact root")
        root = self.root.resolve()
        target = (root / relative).resolve()
        if root not in target.parents:
            raise ValueError("artifact storage path escapes the artifact root")
        content = target.read_bytes()
        digest = "sha256:" + hashlib.sha256(content).hexdigest()
        if digest != artifact.digest or len(content) != artifact.byte_length:
            raise ValueError("artifact integrity verification failed")
        return content
