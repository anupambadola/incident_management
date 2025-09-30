import sqlite3
import openai
import os
import time
import logging
import pandas as pd
from typing import Optional, List, Tuple
from dotenv import load_dotenv

# ---- Setup ---- #
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

DB_FILE = "incidents.db"

# ---- DB Setup ---- #
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS incidents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            Incident_Number TEXT,
            Customer_Name TEXT,
            Organization TEXT,
            Department TEXT,
            Description TEXT,
            Detailed_Description TEXT,
            Reported_Date TEXT,
            Solution TEXT,
            Priority INTEGER
        )
    """)
    conn.commit()
    conn.close()

# ---- Priority Calculation ---- #
def calculate_priority(description: str, detailed_description: str) -> int:
    desc = (description + " " + detailed_description).lower()
    if any(word in desc for word in ["critical", "outage", "failure", "breach", "security"]):
        return 5
    elif any(word in desc for word in ["error", "crash", "slow", "timeout"]):
        return 4
    elif any(word in desc for word in ["bug", "issue", "problem"]):
        return 3
    elif any(word in desc for word in ["request", "access", "minor"]):
        return 2
    return 1

# ---- Similarity Check ---- #
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
def find_solution(new_description: str, new_detailed: str, existing_incidents: List[Tuple]) -> Optional[str]:
    """Check for existing solutions in already loaded incidents (memory lookup)."""
    new_text = f"{new_description} {new_detailed}"
    for desc, det_desc, sol, priority in existing_incidents:
        if check_incident_similarity(new_text, f"{desc} {det_desc}"):
            logging.info(f"Similar incident found with priority {priority}: {desc}")
            return sol
    return None

# ---- Get Solution from LLM ---- #
def generate_solution(description: str, detailed: str) -> str:
    prompt = f"""
    Incident:
    {description}\n{detailed}

    Provide a concise IT support resolution (step-by-step if needed).
    """
    for attempt in range(MAX_RETRIES):
        try:
            response = openai.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": "You are an IT support assistant that provides practical resolutions."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logging.warning(f"Solution generation failed (attempt {attempt+1}): {e}")
            time.sleep(SLEEP_BETWEEN_RETRIES)
    return "No solution could be generated."

# ---- Process Excel ---- #
def process_excel(file_path: str):
    df = pd.read_excel(file_path, sheet_name="Incident Details with REQ and R")

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Load all existing incidents into memory once
    cursor.execute("SELECT Description, Detailed_Description, Solution, Priority FROM incidents ORDER BY Priority DESC")
    existing_incidents = cursor.fetchall()
    db_empty = len(existing_incidents) == 0  # <-- check if DB is empty

    new_records = []

    df = df.sample(n=20, random_state=42) ## You can change/comment it according to your data
    print(f"length is {len(df)}")

    for idx, row in df.iterrows():
        inc_no = row["Incident Number"]
        cust = row["Customer Name"]
        org = row["Organization"]
        dept = row["Department"]
        desc = str(row["Description"])
        det_desc = str(row["Detailed Decription"])
        rep_date = str(row["Reported Date"])

        # Case 1: Empty DB → always generate from LLM
        if db_empty:
            solution = generate_solution(desc, det_desc)
            logging.info(f"Generated new solution for Incident {inc_no} (DB empty)")
        else:
            # Case 2: Try to reuse, otherwise generate
            existing_solution = find_solution(desc, det_desc, existing_incidents)
            if existing_solution:
                solution = existing_solution
                logging.info(f"Reused solution for Incident {inc_no}")
            else:
                solution = generate_solution(desc, det_desc)
                logging.info(f"Generated new solution for Incident {inc_no}")

        priority = calculate_priority(desc, det_desc)

        new_records.append((
            inc_no, cust, org, dept, desc, det_desc, rep_date, solution, priority
        ))

        # Keep memory in sync (but only if DB wasn’t empty initially)
        if not db_empty:
            existing_incidents.append((desc, det_desc, solution, priority))

    # Batch insert all at once
    cursor.executemany("""
        INSERT INTO incidents
        (Incident_Number, Customer_Name, Organization, Department, Description, Detailed_Description, Reported_Date, Solution, Priority)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, new_records)

    conn.commit()
    conn.close()

# ---- Runner ---- #
if __name__ == "__main__":
    init_db()
    process_excel("Incident Details with REQ and Reason Oct23-Mar24-App-Only (1).xlsx")
    print("Incidents processed and pushed into DB successfully.")
