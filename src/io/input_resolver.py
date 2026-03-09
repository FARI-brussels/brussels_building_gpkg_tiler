from __future__ import annotations

import shutil
import zipfile
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Iterator
from urllib.parse import unquote, urlparse
from urllib.request import urlopen

SUPPORTED_URL_SCHEMES = {"file", "http", "https"}


@contextmanager
def resolve_gpkg_input(source: str | Path) -> Iterator[Path]:
    source_value = str(source)
    temporary_dir: TemporaryDirectory[str] | None = None

    try:
        if _is_supported_url(source_value):
            temporary_dir = TemporaryDirectory(prefix="gpkg-tiler-")
            working_dir = Path(temporary_dir.name)
            downloaded_path = _download_to_dir(source_value, working_dir)
            yield _resolve_downloaded_input(downloaded_path, working_dir)
            return

        local_path = Path(source_value).expanduser().resolve()
        if not local_path.exists():
            raise FileNotFoundError(local_path)

        if local_path.is_file() and (
            local_path.suffix.lower() == ".zip" or zipfile.is_zipfile(local_path)
        ):
            temporary_dir = TemporaryDirectory(prefix="gpkg-tiler-")
            yield _extract_single_gpkg(local_path, Path(temporary_dir.name))
            return

        yield local_path
    finally:
        if temporary_dir is not None:
            temporary_dir.cleanup()


def _is_supported_url(value: str) -> bool:
    return urlparse(value).scheme.lower() in SUPPORTED_URL_SCHEMES


def _download_to_dir(url: str, destination_dir: Path) -> Path:
    parsed = urlparse(url)
    filename = Path(unquote(parsed.path)).name or "downloaded_input"
    target_path = destination_dir / filename

    with urlopen(url) as response, target_path.open("wb") as handle:
        shutil.copyfileobj(response, handle)

    return target_path


def _resolve_downloaded_input(downloaded_path: Path, destination_dir: Path) -> Path:
    if downloaded_path.suffix.lower() == ".gpkg":
        return downloaded_path.resolve()
    if downloaded_path.suffix.lower() == ".zip" or zipfile.is_zipfile(downloaded_path):
        return _extract_single_gpkg(downloaded_path, destination_dir)
    raise ValueError(
        f"Unsupported input {downloaded_path.name!r}. Expected a .gpkg file or a .zip archive containing one."
    )


def _extract_single_gpkg(archive_path: Path, destination_dir: Path) -> Path:
    with zipfile.ZipFile(archive_path) as archive:
        gpkg_members = [
            member.filename
            for member in archive.infolist()
            if not member.is_dir() and Path(member.filename).suffix.lower() == ".gpkg"
        ]
        if not gpkg_members:
            raise FileNotFoundError(f"No .gpkg file found in archive: {archive_path}")
        if len(gpkg_members) > 1:
            available = ", ".join(sorted(gpkg_members))
            raise ValueError(
                f"Archive contains multiple .gpkg files; unable to choose automatically: {available}"
            )

        extracted_path = Path(archive.extract(gpkg_members[0], path=destination_dir))
        return extracted_path.resolve()
