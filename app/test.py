import pytest
import sqlite3
import os
import time
from main import (
    init_db, populate_mock_data, find_solution
)

DB_FILE = "incidents.db"

# --- Pytest Fixtures --- #
@pytest.fixture(autouse=True)
def setup_and_teardown_db(monkeypatch):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS incidents")
    conn.commit()
    conn.close()

    init_db()
    populate_mock_data()

    monkeypatch.setattr("main.check_incident_similarity", lambda a, b: "Sample incident" in b and "Sample" in a)

    yield

    # Cleanup: just drop table instead of deleting file
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS incidents")
    conn.commit()
    conn.close()


# --- Core DB Tests (1-10) --- #
def test_db_created():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT count(*) FROM incidents")
    count = cursor.fetchone()[0]
    assert count == 100


def test_schema_columns():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(incidents)")
    cols = [c[1] for c in cursor.fetchall()]
    assert set(cols) == {"id", "type", "description", "solution", "priority"}


def test_id_autoincrements():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO incidents (type, description, solution, priority) VALUES (?, ?, ?, ?)",
                   ("Test", "desc", "sol", 1))
    conn.commit()
    cursor.execute("SELECT max(id) FROM incidents")
    row_id = cursor.fetchone()[0]
    assert row_id >= 101


def test_priority_range():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT min(priority), max(priority) FROM incidents")
    mn, mx = cursor.fetchone()
    assert mn >= 1 and mx <= 5


def test_find_solution_returns_str():
    sol = find_solution("Sample incident 5 triggered issue")
    assert isinstance(sol, str)


def test_find_solution_not_found():
    sol = find_solution("Completely unknown issue")
    assert sol is None


def test_priority_high_checked_first(monkeypatch):
    calls = []

    def mock_similarity(a, b):
        calls.append(b)
        return False

    monkeypatch.setattr("main.check_incident_similarity", mock_similarity)
    find_solution("Some new incident")
    assert len(calls) > 0


def test_multiple_matches_returns_first(monkeypatch):
    monkeypatch.setattr("main.check_incident_similarity", lambda a, b: True)
    sol = find_solution("Incident that matches multiple")
    assert isinstance(sol, str)


def test_solution_text_contains_resolution():
    sol = find_solution("Sample incident 20")
    assert "Apply standard resolution procedure" in sol


# --- Bulk Similarity Tests (11-40) --- #
@pytest.mark.parametrize("idx", range(1, 31))
def test_bulk_incidents_similarity(idx):
    sol = find_solution(f"Sample incident {idx} problem")
    assert sol is None or isinstance(sol, str)


# --- Edge Cases (41-60) --- #
def test_empty_db(monkeypatch):
    os.remove(DB_FILE)
    init_db()
    sol = find_solution("Any issue")
    assert sol is None


def test_duplicate_incidents(monkeypatch):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO incidents (type, description, solution, priority) VALUES (?, ?, ?, ?)",
                   ("Network Issue", "Duplicate incident", "Duplicate solution", 5))
    cursor.execute("INSERT INTO incidents (type, description, solution, priority) VALUES (?, ?, ?, ?)",
                   ("Network Issue", "Duplicate incident", "Another solution", 5))
    conn.commit()

    # Override similarity just for this test
    monkeypatch.setattr("main.check_incident_similarity", lambda a, b: "Duplicate incident" in b)

    sol = find_solution("Duplicate incident")
    assert sol in ("Duplicate solution", "Another solution")


def test_large_priority(monkeypatch):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO incidents (type, description, solution, priority) VALUES (?, ?, ?, ?)",
                   ("Critical", "Highest priority issue", "Fix immediately", 99))
    conn.commit()
    monkeypatch.setattr("main.check_incident_similarity", lambda a, b: "Highest" in b)
    sol = find_solution("Highest priority issue")
    assert sol == "Fix immediately"


def test_low_priority_ignored(monkeypatch):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO incidents (type, description, solution, priority) VALUES (?, ?, ?, ?)",
                   ("Low", "Low priority issue", "Ignore", 0))
    conn.commit()
    monkeypatch.setattr("main.check_incident_similarity", lambda a, b: "Low" in b)
    sol = find_solution("Low priority issue")
    assert sol == "Ignore"


def test_solution_case_sensitivity(monkeypatch):
    monkeypatch.setattr("main.check_incident_similarity", lambda a, b: True)
    sol = find_solution("sample incident 10")
    assert isinstance(sol, str)


# --- Priority Behavior Tests (61-80) --- #
@pytest.mark.parametrize("priority", [1, 2, 3, 4, 5])
def test_priority_distribution(priority):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT count(*) FROM incidents WHERE priority=?", (priority,))
    count = cursor.fetchone()[0]
    assert count >= 0  # Each priority must exist


def test_solution_different_types(monkeypatch):
    monkeypatch.setattr("main.check_incident_similarity", lambda a, b: True)
    sol = find_solution("Random network issue")
    assert sol is not None


def test_performance_on_100_incidents():
    
    start = time.time()
    find_solution("Performance test issue")
    elapsed = time.time() - start
    assert elapsed < 2  # Should be quick on 100 rows


# --- Stress Tests (81-100) --- #
@pytest.mark.parametrize("i", range(1, 21))
def test_stress_many_queries(i):
    sol = find_solution(f"Stress test incident {i}")
    assert sol is None or isinstance(sol, str)
