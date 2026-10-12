"""Opt-in real PostgreSQL checks, using session-local synthetic tables only."""

from contextlib import contextmanager
import os
from pathlib import Path
from uuid import uuid4

import pytest

from backend.db import candidates
from backend.db.connection import get_postgres_connection

pytestmark = pytest.mark.skipif(
    os.environ.get("JJA_SEARCH_DB_TESTS") != "1",
    reason="Set JJA_SEARCH_DB_TESTS=1 for temporary-table PostgreSQL checks.",
)


@pytest.fixture
def search_db(monkeypatch):
    db = get_postgres_connection()
    try:
        db.execute("SET LOCAL search_path TO pg_temp, public")
        db.execute("""
            CREATE TEMP TABLE people (id uuid PRIMARY KEY, full_name text);
            CREATE TEMP TABLE companies (id uuid PRIMARY KEY, name text);
            CREATE TEMP TABLE candidates (id uuid PRIMARY KEY, person_id uuid,
                current_company_id uuid, current_title text, candidate_status text,
                resume_updated_at timestamptz);
            CREATE TEMP TABLE documents (id uuid PRIMARY KEY, title text,
                source_uri text, resume_updated_at timestamptz,
                extracted_text text, document_type text);
            CREATE TEMP TABLE document_links (candidate_id uuid, document_id uuid,
                relationship_type text);
        """)
        migration = Path("supabase/migrations/0017_indexed_resume_search.sql").read_text()
        db.execute(migration.replace("public.", "pg_temp.")
                   .replace("BEGIN;", "").replace("COMMIT;", ""))
        company_id = uuid4()
        db.execute("INSERT INTO companies VALUES (%s, 'Pirum Systems')", (company_id,))
        ids = []
        for name, title, body, relationship in [
            ("Person Alpha", "Senior Engineer", "SFTR securities lending", "current_resume"),
            ("Person Beta", "Analyst", "Python repo repurchase agreements", "current_resume"),
            ("Person Archive", "Analyst", "SFTR", "historical_resume"),
        ]:
            candidate_id, person_id, document_id = uuid4(), uuid4(), uuid4()
            ids.append(str(candidate_id))
            db.execute("INSERT INTO people VALUES (%s, %s)", (person_id, name))
            db.execute("INSERT INTO candidates VALUES (%s,%s,%s,%s,'active',now())",
                       (candidate_id, person_id, company_id, title))
            db.execute("INSERT INTO documents (id,title,extracted_text,document_type) VALUES (%s,%s,%s,'resume')",
                       (document_id, name + " CV", body))
            db.execute("INSERT INTO document_links VALUES (%s,%s,%s)",
                       (candidate_id, document_id, relationship))

        @contextmanager
        def connection():
            yield db

        monkeypatch.setattr(candidates, "postgres_connection", connection)
        yield db, ids
    finally:
        db.rollback()
        db.close()


def test_indexed_search_preserves_cross_field_boolean_and_current_cv_scope(search_db):
    _, ids = search_db
    for query, expected in [
        ("SFTR", [ids[0]]),
        ("engineer SFTR", [ids[0]]),
        ('"securities lending"', [ids[0]]),
        ("SFTR OR python", ids[:2]),
        ("Pirum -python", [ids[0]]),
        ("-python", [ids[0]]),
        ("nonexistent", []),
    ]:
        result = candidates.search_candidates_by_resume_text(query=query, limit=10)
        assert sorted(str(row["candidate_id"]) for row in result) == sorted(expected)


def test_search_vector_updates_automatically_and_company_lookup_works(search_db):
    db, ids = search_db
    db.execute("UPDATE documents SET extracted_text = 'EquiLend SFTR' WHERE title = 'Person Beta CV'")
    result = candidates.search_candidates_by_resume_text(query="EquiLend", limit=5)
    assert [str(row["candidate_id"]) for row in result] == [ids[1]]
    employer = candidates.search_candidates_by_company_name(company_name="Pirum", limit=5)
    assert {str(row["candidate_id"]) for row in employer} == set(ids[:2])
    mentions = candidates.search_candidates_by_company_name(company_name="EquiLend", limit=5)
    assert [str(row["candidate_id"]) for row in mentions] == [ids[1]]
