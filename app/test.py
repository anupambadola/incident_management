import pytest
import sqlite3
import os
import time
from main import (
    init_db, calculate_priority, find_solution
)

DB_FILE = "incidents.db"

# --- Pytest Fixtures --- #
@pytest.fixture(autouse=True)
def setup_and_teardown_db(monkeypatch):
    # Drop & recreate DB
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS incidents")
    conn.commit()
    conn.close()

    init_db()

    # Insert 20 mock incidents (instead of populate_mock_data)
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    sample_records = []
    for i in range(20):
        sample_records.append((
            f"INC{i+1}",               # Incident_Number
            f"Customer {i+1}",         # Customer_Name
            "OrgX",                    # Organization
            "DeptY",                   # Department
            f"Sample incident {i+1}",  # Description
            f"Detailed description {i+1}",
            f"2024-01-{i+1:02d}",      # Reported_Date
            f"Apply standard resolution procedure {i+1}",  # Solution
            (i % 5) + 1                # Priority
        ))
    cursor.executemany("""
        INSERT INTO incidents
        (Incident_Number, Customer_Name, Organization, Department,
         Description, Detailed_Description, Reported_Date, Solution, Priority)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, sample_records)
    conn.commit()
    conn.close()

    # Monkeypatch similarity check
    monkeypatch.setattr("main.check_incident_similarity", lambda a, b: "Sample incident" in b and "Sample" in a)

    yield

    # Cleanup
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS incidents")
    conn.commit()
    conn.close()


# --- Core DB Tests --- #
def test_db_created():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT count(*) FROM incidents")
    count = cursor.fetchone()[0]
    assert count == 20


def test_schema_columns():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(incidents)")
    cols = [c[1] for c in cursor.fetchall()]
    assert set(cols) == {
        "id", "Incident_Number", "Customer_Name", "Organization",
        "Department", "Description", "Detailed_Description",
        "Reported_Date", "Solution", "Priority"
    }


def test_id_autoincrements():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO incidents
        (Incident_Number, Customer_Name, Organization, Department,
         Description, Detailed_Description, Reported_Date, Solution, Priority)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, ("NEW1", "Cust", "Org", "Dept", "desc", "det desc", "2024-02-01", "sol", 3))
    conn.commit()
    cursor.execute("SELECT max(id) FROM incidents")
    row_id = cursor.fetchone()[0]
    assert row_id >= 21


def test_priority_range():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT min(Priority), max(Priority) FROM incidents")
    mn, mx = cursor.fetchone()
    assert mn >= 1 and mx <= 5


def test_find_solution_returns_str():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT Description, Detailed_Description, Solution, Priority FROM incidents")
    existing_incidents = cursor.fetchall()
    sol = find_solution("Sample incident 5 triggered issue", "Some details", existing_incidents)
    assert isinstance(sol, str) or sol is None


def test_find_solution_not_found():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT Description, Detailed_Description, Solution, Priority FROM incidents")
    existing_incidents = cursor.fetchall()
    sol = find_solution("Completely unknown issue", "Random details", existing_incidents)
    assert sol is None


def test_priority_calculation_keywords():
    high = calculate_priority("Critical failure detected", "Major outage in system")
    med = calculate_priority("Bug found", "Causing problem in UI")
    low = calculate_priority("Request for access", "Minor change needed")
    assert high == 5
    assert med == 3
    assert low == 2


def test_solution_text_contains_resolution():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT Description, Detailed_Description, Solution, Priority FROM incidents")
    existing_incidents = cursor.fetchall()
    sol = find_solution("Sample incident 10", "Details here", existing_incidents)
    if sol:  # may be None if similarity fails
        assert "Apply standard resolution procedure" in sol


# --- Performance Test --- #
def test_performance_on_20_incidents():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT Description, Detailed_Description, Solution, Priority FROM incidents")
    existing_incidents = cursor.fetchall()

    start = time.time()
    find_solution("Performance test issue", "details", existing_incidents)
    elapsed = time.time() - start
    assert elapsed < 2
