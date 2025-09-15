"""State file persistence helpers with atomic writes and checksums."""

import json
import os
from pathlib import Path
from typing import Dict, Any, Optional
import hashlib


class StateFileHandler:
    """Handles atomic state file operations with integrity checks."""

    @staticmethod
    def atomic_write(file_path: Path, data: Dict[str, Any]) -> None:
        """Write data to file atomically using temp file + rename.

        Args:
            file_path: Target file path
            data: Data to write as JSON

        Raises:
            OSError: If write or rename fails
        """
        # Ensure parent directory exists
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Write to temp file
        temp_path = file_path.with_suffix('.tmp')
        try:
            with open(temp_path, 'w') as f:
                json.dump(data, f, indent=2)
                f.flush()
                os.fsync(f.fileno())  # Ensure data is written to disk

            # Atomic rename
            temp_path.replace(file_path)
        except Exception:
            # Clean up temp file on failure
            if temp_path.exists():
                temp_path.unlink()
            raise

    @staticmethod
    def read_with_validation(file_path: Path) -> Dict[str, Any]:
        """Read JSON file with validation.

        Args:
            file_path: Path to JSON file

        Returns:
            Parsed JSON data

        Raises:
            FileNotFoundError: If file doesn't exist
            json.JSONDecodeError: If file is not valid JSON
        """
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        with open(file_path, 'r') as f:
            return json.load(f)

    @staticmethod
    def compute_checksum(file_path: Path) -> str:
        """Compute SHA256 checksum of file.

        Args:
            file_path: Path to file

        Returns:
            Checksum string in format "sha256:hexdigest"

        Raises:
            FileNotFoundError: If file doesn't exist
        """
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        sha256_hash = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256_hash.update(chunk)

        return f"sha256:{sha256_hash.hexdigest()}"

    @staticmethod
    def verify_checksum(file_path: Path, expected_checksum: str) -> bool:
        """Verify file checksum matches expected value.

        Args:
            file_path: Path to file
            expected_checksum: Expected checksum string

        Returns:
            True if checksum matches, False otherwise
        """
        try:
            actual_checksum = StateFileHandler.compute_checksum(file_path)
            return actual_checksum == expected_checksum
        except FileNotFoundError:
            return False

    @staticmethod
    def create_backup(source_path: Path, backup_suffix: str) -> Optional[Path]:
        """Create a backup copy of a file.

        Args:
            source_path: Path to source file
            backup_suffix: Suffix for backup file (e.g., ".step_Name.bak")

        Returns:
            Path to backup file if created, None if source doesn't exist
        """
        if not source_path.exists():
            return None

        backup_path = source_path.parent / f"{source_path.name}{backup_suffix}"

        # Copy file content (not using shutil to avoid dependency)
        with open(source_path, 'rb') as src:
            with open(backup_path, 'wb') as dst:
                dst.write(src.read())

        return backup_path

    @staticmethod
    def find_latest_backup(directory: Path, pattern: str = "state.json.step_*.bak") -> Optional[Path]:
        """Find the most recent backup file.

        Args:
            directory: Directory to search
            pattern: Glob pattern for backup files

        Returns:
            Path to most recent backup, or None if no backups found
        """
        backup_files = sorted(
            directory.glob(pattern),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )

        return backup_files[0] if backup_files else None