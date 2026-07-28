"""Tests for restartable Linked Helper backup batch orchestration."""

import json

import pytest

from scripts import run_linkedin_helper_backup_batches as subject


def test_resolve_run_state_starts_fresh() -> None:
    offset, cumulative = subject._resolve_run_state(
        checkpoint=None,
        dropbox_path="/backup.lhd2",
        backup_sha256="abc",
        total_people=100,
        start_offset=40,
    )

    assert offset == 40
    assert cumulative == subject._empty_cumulative_counts()


def test_resolve_run_state_resumes_matching_checkpoint() -> None:
    checkpoint = {
        "version": subject.CHECKPOINT_VERSION,
        "dropbox_path": "/backup.lhd2",
        "backup_sha256": "abc",
        "total_people": 100,
        "next_offset": 60,
        "cumulative": {
            "people_persisted": 38,
            "companies_persisted": 100,
            "roles_persisted": 200,
            "skills_persisted": 300,
            "batches_completed": 3,
        },
    }

    offset, cumulative = subject._resolve_run_state(
        checkpoint=checkpoint,
        dropbox_path="/backup.lhd2",
        backup_sha256="abc",
        total_people=100,
        start_offset=0,
    )

    assert offset == 60
    assert cumulative["people_persisted"] == 38
    assert cumulative["batches_completed"] == 3


def test_resolve_run_state_rejects_different_backup() -> None:
    checkpoint = {
        "version": subject.CHECKPOINT_VERSION,
        "dropbox_path": "/backup.lhd2",
        "backup_sha256": "different",
        "total_people": 100,
        "next_offset": 20,
    }

    with pytest.raises(SystemExit, match="backup_sha256"):
        subject._resolve_run_state(
            checkpoint=checkpoint,
            dropbox_path="/backup.lhd2",
            backup_sha256="abc",
            total_people=100,
            start_offset=0,
        )


def test_checkpoint_write_is_restartable(tmp_path) -> None:
    checkpoint_path = tmp_path / "linkedin-helper.checkpoint.json"
    payload = {"version": 1, "next_offset": 20}

    subject._write_checkpoint(checkpoint_path, payload)

    assert subject._load_checkpoint(checkpoint_path) == payload
    assert not checkpoint_path.with_suffix(".json.tmp").exists()
    assert json.loads(checkpoint_path.read_text(encoding="utf-8")) == payload


def test_add_persistence_counts_accumulates_completed_batch() -> None:
    updated = subject._add_persistence_counts(
        subject._empty_cumulative_counts(),
        {
            "people_persisted": 20,
            "companies_persisted": 42,
            "roles_persisted": 75,
            "skills_persisted": 120,
        },
    )

    assert updated == {
        "people_persisted": 20,
        "companies_persisted": 42,
        "roles_persisted": 75,
        "skills_persisted": 120,
        "batches_completed": 1,
    }


def test_parser_accepts_larger_related_company_limit() -> None:
    args = subject.build_parser().parse_args(
        ["--max-related-companies", "500"]
    )

    assert args.max_related_companies == 500
