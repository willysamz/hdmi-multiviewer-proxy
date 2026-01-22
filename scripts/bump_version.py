#!/usr/bin/env python3
"""Bump version across all files following semver."""

import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent

VERSION_FILES = [
    ("VERSION", r"^(\d+\.\d+\.\d+)$", "{version}"),
    ("app/__init__.py", r'__version__ = "(\d+\.\d+\.\d+)"', '__version__ = "{version}"'),
    ("pyproject.toml", r'^version = "(\d+\.\d+\.\d+)"', 'version = "{version}"'),
    ("chart/Chart.yaml", r"^version: (\d+\.\d+\.\d+)$", "version: {version}"),
    ("chart/Chart.yaml", r'^appVersion: "(\d+\.\d+\.\d+)"$', 'appVersion: "{version}"'),
]


def get_current_version() -> str:
    """Read current version from VERSION file."""
    version_file = PROJECT_ROOT / "VERSION"
    return version_file.read_text().strip()


def parse_version(version: str) -> tuple[int, int, int]:
    """Parse semver string into tuple."""
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)$", version)
    if not match:
        raise ValueError(f"Invalid semver: {version}")
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def bump_version(current: str, bump_type: str) -> str:
    """Bump version according to semver rules."""
    major, minor, patch = parse_version(current)

    if bump_type == "major":
        return f"{major + 1}.0.0"
    elif bump_type == "minor":
        return f"{major}.{minor + 1}.0"
    elif bump_type == "patch":
        return f"{major}.{minor}.{patch + 1}"
    else:
        raise ValueError(f"Invalid bump type: {bump_type}. Use: major, minor, patch")


def update_file(filepath: str, pattern: str, replacement: str, new_version: str) -> bool:
    """Update version in a file."""
    full_path = PROJECT_ROOT / filepath
    if not full_path.exists():
        print(f"  Warning: {filepath} not found, skipping")
        return False

    content = full_path.read_text()
    new_replacement = replacement.format(version=new_version)

    # Use multiline mode for patterns that match line start
    flags = re.MULTILINE if pattern.startswith("^") else 0
    new_content, count = re.subn(pattern, new_replacement, content, flags=flags)

    if count == 0:
        print(f"  Warning: Pattern not found in {filepath}")
        return False

    full_path.write_text(new_content)
    print(f"  Updated {filepath}")
    return True


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: bump_version.py <major|minor|patch|VERSION>")
        print()
        print("Examples:")
        print("  bump_version.py patch    # 0.1.0 -> 0.1.1")
        print("  bump_version.py minor    # 0.1.0 -> 0.2.0")
        print("  bump_version.py major    # 0.1.0 -> 1.0.0")
        print("  bump_version.py 1.2.3    # Set specific version")
        sys.exit(1)

    arg = sys.argv[1]
    current = get_current_version()

    # Determine new version
    if arg in ("major", "minor", "patch"):
        new_version = bump_version(current, arg)
    else:
        # Validate it's a valid semver
        parse_version(arg)
        new_version = arg

    print(f"Bumping version: {current} -> {new_version}")
    print()

    # Update all files
    for filepath, pattern, replacement in VERSION_FILES:
        update_file(filepath, pattern, replacement, new_version)

    print()
    print(f"Version bumped to {new_version}")
    print()
    print("Next steps:")
    print(f"  git add -A")
    print(f"  git commit -m 'chore: bump version to {new_version}'")
    print(f"  git tag v{new_version}")
    print(f"  git push origin main --tags")


if __name__ == "__main__":
    main()
