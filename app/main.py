import sqlite3
import random
import openai
import os
import time
import logging
from typing import Optional
from dotenv import load_dotenv

# Load API key
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")
MODEL = "gpt-4o"

MAX_RETRIES = 3
SLEEP_BETWEEN_RETRIES = 2

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    filename="incident_solution_retrieval.log",
    filemode="a"
)

# ---- SQL Setup ---- #
DB_FILE = "incidents.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS incidents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT,
            description TEXT,
            solution TEXT,
            priority INTEGER
        )
    """)
    conn.commit()
    conn.close()


# ---- Generate Mock Data (100 incidents) ---- #
INCIDENT_TYPES = [
    "Network Issue", "Application Crash", "Security Alert", "Hardware Failure",
    "User Error", "Performance Degradation", "Software Bug", "Access Request",
    "Service Outage", "Database Error", "Configuration Issue"
]

def populate_mock_data():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    sample_incidents = []
    for i in range(1, 101):
        inc_type = random.choice(INCIDENT_TYPES)
        description = f"Sample incident {i}: {inc_type} occurred due to random event."
        solution = f"Apply standard resolution procedure for {inc_type} (auto-generated)."
        priority = random.randint(1, 5)  # 1=low, 5=high
        sample_incidents.append((inc_type, description, solution, priority))

    cursor.executemany(
        "INSERT INTO incidents (type, description, solution, priority) VALUES (?, ?, ?, ?)",
        sample_incidents
    )
    conn.commit()
    conn.close()


# ---- LLM Similarity Check ---- #
SIMILARITY_PROMPT = """
You are an assistant that checks whether two IT incidents describe the SAME issue.

Incident A:
{incident_a}

Incident B:
{incident_b}

Respond with ONLY one word:
- "YES" if they are essentially the same incident
- "NO" if they are different
"""

def check_incident_similarity(incident_a: str, incident_b: str) -> bool:
    """Uses LLM to check if two incidents are the same."""
    prompt = SIMILARITY_PROMPT.format(incident_a=incident_a, incident_b=incident_b)

    for attempt in range(MAX_RETRIES):
        try:
            response = openai.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": "You are an assistant for comparing IT incidents."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.0,
            )
            result = response.choices[0].message.content.strip().upper()
            return result == "YES"
        except Exception as e:
            logging.warning(f"Similarity check failed (attempt {attempt+1}): {e}")
            time.sleep(SLEEP_BETWEEN_RETRIES)

    logging.error("Failed to check similarity after retries.")
    return False


# ---- Solution Retrieval ---- #
def find_solution(new_incident: str) -> Optional[str]:
    """
    Given a new incident, check if a similar incident exists in DB.
    Incidents are checked in order of priority (high first).
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT description, solution, priority FROM incidents ORDER BY priority DESC")
    all_incidents = cursor.fetchall()
    conn.close()

    for desc, sol, priority in all_incidents:
        if check_incident_similarity(new_incident, desc):
            logging.info(f"Similar incident found with priority {priority}: {desc}")
            return sol

    logging.info("No similar incident found in DB.")
    return None


# ---- Demo Runner ---- #
if __name__ == "__main__":
    # Initialize DB and populate with mock data (run once)
    init_db()
    populate_mock_data()

    test_incidents = [
        "The database is throwing random connection errors.",
        "Application crashes whenever the submit button is clicked.",
        "Firewall detected an intrusion attempt from suspicious IP.",
        "Server disk space almost full causing slowness."
    ]

    for inc in test_incidents:
        solution = find_solution(inc)
        if solution:
            print(f"Incident: {inc}\n → Solution: {solution}\n")
        else:
            print(f"Incident: {inc}\n → No solution found in DB.\n")
