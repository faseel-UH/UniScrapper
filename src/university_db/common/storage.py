from __future__ import annotations

from pathlib import Path

from university_db.common.hashing import sha256_text


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_snapshot(content: bytes, output_dir: Path, extension: str) -> tuple[str, str]:
    ensure_dir(output_dir)
    digest = sha256_text(content.decode("utf-8", errors="ignore") if extension == "html" else content.hex())
    file_path = output_dir / f"{digest}.{extension}"
    file_path.write_bytes(content)
    return str(file_path), digest
