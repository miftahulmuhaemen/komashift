import json
import logging
import os
import re
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple, Callable

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from src.version import __version__

logger = logging.getLogger(__name__)

DEFAULT_REPO = "sahana/win-folder-thumbnail"


@dataclass
class ReleaseInfo:
    version: str
    tag_name: str
    release_notes: str
    setup_asset_url: Optional[str]
    setup_asset_name: Optional[str]
    setup_size_bytes: int


def parse_semver(v: str) -> Tuple[int, int, int]:
    clean = re.sub(r'^[^\d]*', '', v.strip())
    parts = clean.split('.')
    try:
        major = int(parts[0]) if len(parts) > 0 else 0
        minor = int(parts[1]) if len(parts) > 1 else 0
        patch = int(parts[2]) if len(parts) > 2 else 0
        return (major, minor, patch)
    except ValueError:
        return (0, 0, 0)


def is_newer_version(latest_str: str, current_str: str = __version__) -> bool:
    return parse_semver(latest_str) > parse_semver(current_str)


class UpdateCheckerService:
    """Checks GitHub Releases API for new KomaShift versions."""

    def __init__(self, repo: str = DEFAULT_REPO):
        self.repo = repo

    def check_for_updates(self, current_version: str = __version__) -> Optional[ReleaseInfo]:
        """
        Queries the GitHub API for latest release.
        Returns ReleaseInfo if a newer release exists, or None.
        """
        url = f"https://api.github.com/repos/{self.repo}/releases/latest"
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": f"KomaShift-App/{current_version}",
                "Accept": "application/vnd.github.v3+json",
            }
        )

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status != 200:
                    return None
                data = json.loads(resp.read().decode("utf-8"))

            tag_name = data.get("tag_name", "")
            latest_version = tag_name.lstrip("v")
            if not is_newer_version(latest_version, current_version):
                return None

            setup_url = None
            setup_name = None
            setup_size = 0

            # Scan assets for KomaShift-Setup or .exe installer
            for asset in data.get("assets", []):
                name = asset.get("name", "")
                if ("setup" in name.lower() or "komashift" in name.lower()) and name.endswith(".exe"):
                    setup_url = asset.get("browser_download_url")
                    setup_name = name
                    setup_size = int(asset.get("size", 0))
                    break

            return ReleaseInfo(
                version=latest_version,
                tag_name=tag_name,
                release_notes=data.get("body", ""),
                setup_asset_url=setup_url,
                setup_asset_name=setup_name,
                setup_size_bytes=setup_size
            )
        except Exception as e:
            logger.debug(f"Update check completed without finding updates: {e}")
            return None


class UpdateCheckWorker(QThread):
    """Background worker thread to check for updates without freezing UI."""
    update_available = pyqtSignal(object)  # emits ReleaseInfo

    def __init__(self, repo: str = DEFAULT_REPO, parent=None):
        super().__init__(parent)
        self.checker = UpdateCheckerService(repo=repo)

    def run(self):
        info = self.checker.check_for_updates()
        if info:
            self.update_available.emit(info)
