"""Build helpers for LabelOps release packaging."""

from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path
from typing import Iterable

RELEASE_PREFIX = "LabelOps"
STARTER_CONFIG_FILES = (
    Path("config") / "clients.yaml",
    Path("config") / "telegram_allowlist.json",
)
STARTER_ASSET_FILES = (Path("assets") / "ClickDrop_import_template_no_header.xlsx",)


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def read_version(root: Path) -> str:
    version_file = root / "app" / "version.py"
    if not version_file.exists():
        raise FileNotFoundError(f"Version file not found: {version_file}")
    namespace: dict[str, str] = {}
    exec(version_file.read_text(encoding="utf-8"), namespace)
    version = namespace.get("__version__")
    if not version:
        raise ValueError("__version__ not defined in app/version.py")
    return str(version)


def release_dir_name(version: str, date: dt.date | None = None) -> str:
    build_date = date or dt.date.today()
    return f"{RELEASE_PREFIX}_{version}_{build_date:%Y%m%d}"


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def copy_files(files: Iterable[Path], destination: Path) -> None:
    ensure_dir(destination)
    for file_path in files:
        source = repo_root() / file_path
        if not source.exists():
            raise FileNotFoundError(f"Required file missing: {source}")
        target = destination / file_path.name
        target.write_bytes(source.read_bytes())


def write_build_info(release_dir: Path, git_commit: str | None) -> Path:
    version = read_version(repo_root())
    build_info_path = release_dir / "BUILD_INFO.txt"
    timestamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    commit_value = git_commit or "unknown"
    content = (
        "LabelOps Build Information\n"
        f"Version: {version}\n"
        f"Build date: {timestamp}\n"
        f"Git commit: {commit_value}\n"
    )
    build_info_path.write_text(content, encoding="utf-8")
    return build_info_path


def cmd_print_version(_: argparse.Namespace) -> None:
    print(read_version(repo_root()))


def cmd_release_dir(args: argparse.Namespace) -> None:
    root = repo_root()
    version = read_version(root)
    release_dir = Path(args.dist_root) / release_dir_name(version)
    ensure_dir(release_dir)
    print(str(release_dir))


def cmd_copy_starters(args: argparse.Namespace) -> None:
    release_dir = Path(args.release_dir)
    if not release_dir.exists():
        raise FileNotFoundError(f"Release directory does not exist: {release_dir}")
    copy_files(STARTER_CONFIG_FILES, release_dir / "config")
    copy_files(STARTER_ASSET_FILES, release_dir / "assets")


def cmd_write_build_info(args: argparse.Namespace) -> None:
    release_dir = Path(args.release_dir)
    if not release_dir.exists():
        raise FileNotFoundError(f"Release directory does not exist: {release_dir}")
    write_build_info(release_dir, args.git_commit)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="LabelOps build helper utilities.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    parser_version = subparsers.add_parser("print-version", help="Print app version.")
    parser_version.set_defaults(func=cmd_print_version)

    parser_release = subparsers.add_parser(
        "release-dir", help="Create and print the release directory path."
    )
    parser_release.add_argument(
        "--dist-root",
        required=True,
        help="Base folder for dist outputs (e.g., D:\\LabelOps\\dist).",
    )
    parser_release.set_defaults(func=cmd_release_dir)

    parser_copy = subparsers.add_parser(
        "copy-starters", help="Copy starter config/assets into release directory."
    )
    parser_copy.add_argument("--release-dir", required=True)
    parser_copy.set_defaults(func=cmd_copy_starters)

    parser_build_info = subparsers.add_parser(
        "write-build-info", help="Write BUILD_INFO.txt into the release directory."
    )
    parser_build_info.add_argument("--release-dir", required=True)
    parser_build_info.add_argument("--git-commit", default="")
    parser_build_info.set_defaults(func=cmd_write_build_info)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
