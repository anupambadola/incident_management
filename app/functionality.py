from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional
import sqlite3
import logging

# Import all helper functions and constants from main.py
import main  

app = FastAPI(title="Incident Solution API")

# ---- Pydantic Model ---- #
class IncidentRequest(BaseModel):
    incident_num: str
    customer_name: str
    organization: str
    department: str
    description: str
    detailed_description: str
    reported_date: str


# ---- DB Helpers (thin wrappers using main.DB_FILE) ---- #
def load_existing_incidents():
    conn = sqlite3.connect(main.DB_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT Description, Detailed_Description, Solution, Priority FROM incidents ORDER BY Priority DESC"
    )
    rows = cursor.fetchall()
    conn.close()
    return rows


def save_incident(incident: IncidentRequest, solution: str, priority: int):
    conn = sqlite3.connect(main.DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO incidents 
        (incident_number, customer_name, organization, department, description, detailed_description, reported_date, solution, priority)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        incident.incident_num,
        incident.customer_name,
        incident.organization,
        incident.department,
        incident.description,
        incident.detailed_description,
        incident.reported_date,
        solution,
        priority
    ))
    conn.commit()
    conn.close()


# ---- FastAPI Endpoint ---- #
@app.post("/get_solution")
def get_solution(incident: IncidentRequest):
    existing_incidents = load_existing_incidents()
    db_empty = len(existing_incidents) == 0

    # Case 1: Empty DB → always generate
    if db_empty:
        solution = main.generate_solution(incident.description, incident.detailed_description)
        logging.info("Generated new solution (DB empty).")
    else:
        # Case 2: Try reuse, else generate
        existing_solution = main.find_solution(
            incident.description, incident.detailed_description, existing_incidents
        )
        if existing_solution:
            solution = existing_solution
            logging.info("Reused existing solution.")
        else:
            solution = main.generate_solution(incident.description, incident.detailed_description)
            logging.info("Generated new solution.")

    # Calculate priority
    priority = main.calculate_priority(incident.description, incident.detailed_description)

    # Save to DB
    save_incident(incident, solution, priority)

    return {"priority": priority, "solution": solution}
