"""Tests for the controlled Supabase migration runner."""

import pytest

from scripts.apply_supabase_migration import resolve_migration_path


def test_resolve_migration_path_accepts_tracked_filename() -> None:
    path = resolve_migration_path("0010_person_skills.sql")
    assert path.name == "0010_person_skills.sql"


def test_resolve_migration_path_rejects_directory_traversal() -> None:
    with pytest.raises(ValueError, match="filename"):
        resolve_migration_path("../secrets.sql")
