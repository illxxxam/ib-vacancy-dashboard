"""
init_db.py — Database initialization and vacancy loading for Category 6 (Information Security).
Professions: Penetration Tester, Information Security Analyst, SOC Analyst, GRC Specialist.
"""
import json
import re
import sqlite3
import os
from bs4 import BeautifulSoup


PROF_KEYWORDS = {
    "Penetration Tester": [
        "пентестер", "пентест", "penetration test", "pentest",
        "red team", "redteam", "red-team", "тестирование на проникновение",
    ],
    "Information Security Analyst": [
        "аналитик иб", "аналитик информационной безопасности",
        "information security analyst", "аналитик кибербезопасности",
        "аналитик по иб", "security analyst",
    ],
    "SOC Analyst": [
        "soc analyst", "soc-аналитик", "soc аналитик", "аналитик soc",
        "аналитик центра мониторинга", "soc-инженер", "soc инженер",
    ],
    "GRC Specialist": [
        "grc", "compliance", "комплаенс", "cybersecurity risk",
        "security compliance", "иб-риск", "управление рисками иб",
        "информационной безопасности (compliance)",
    ],
}

REQ_SECTION_KEYWORDS = [
    "требования", "необходимые компетенции", "компетенции",
    "от вас", "ожидаем", "необходимо", "ключевые навыки",
    "requirements", "что нужно уметь", "ищем", "нам нужен",
    "вам предстоит", "будет плюсом", "будет преимуществом",
    "желательно", "обязательно", "кандидат должен",
]
COND_SECTION_KEYWORDS = [
    "мы предлагаем", "что мы предлагаем", "условия", "предлагаем",
    "у нас", "мы готовы", "benefits", "offer",
    "обязанности", "задачи", "что нужно делать", "что предстоит",
]


def clean_html(html: str) -> str:
    """Strip HTML tags and normalise whitespace."""
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    return " ".join(soup.get_text(" ", strip=True).split())


def extract_sections(description_html: str):
    """Return (requirements: list[str], conditions: list[str]) extracted from HTML."""
    soup = BeautifulSoup(description_html, "html.parser")
    lines = [ln.strip() for ln in soup.get_text("\n", strip=True).split("\n") if ln.strip()]

    requirements, conditions = [], []
    mode = None
    for line in lines:
        ll = line.lower()
        if any(kw in ll for kw in REQ_SECTION_KEYWORDS):
            mode = "req"
        elif any(kw in ll for kw in COND_SECTION_KEYWORDS):
            mode = "cond"
        elif mode == "req" and len(line) > 5:
            requirements.append(line)
        elif mode == "cond" and len(line) > 5:
            conditions.append(line)

    # Fallback: if nothing found, split by list items
    if not requirements:
        for li in soup.find_all("li"):
            txt = li.get_text(strip=True)
            if len(txt) > 8:
                requirements.append(txt)

    return requirements, conditions


def classify_vacancy(name: str) -> str | None:
    """Return the profession category for a vacancy name, or None."""
    name_lower = name.lower()
    for prof, keywords in PROF_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in name_lower:
                return prof
    return None


def init_database(db_path: str = "vacancies.db"):
    """Create SQLite schema."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS vacancies (
            id          TEXT PRIMARY KEY,
            source      TEXT,
            url         TEXT,
            name        TEXT,
            employer    TEXT,
            description TEXT,
            profession  TEXT,
            plain_text  TEXT
        );
        CREATE TABLE IF NOT EXISTS requirements (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            vacancy_id  TEXT,
            text        TEXT,
            FOREIGN KEY (vacancy_id) REFERENCES vacancies(id)
        );
        CREATE TABLE IF NOT EXISTS conditions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            vacancy_id  TEXT,
            text        TEXT,
            FOREIGN KEY (vacancy_id) REFERENCES vacancies(id)
        );
        CREATE INDEX IF NOT EXISTS idx_prof ON vacancies(profession);
    """)
    conn.commit()
    return conn


def load_vacancies(jsonl_path: str, db_path: str = "vacancies.db"):
    """Read JSONL, filter category-6 vacancies, persist to SQLite."""
    conn = init_database(db_path)
    cur = conn.cursor()

    inserted = 0
    skipped = 0
    by_prof = {k: 0 for k in PROF_KEYWORDS}

    with open(jsonl_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue

            if rec.get("download_status") != "ok":
                continue

            name = rec.get("name", "")
            profession = classify_vacancy(name)
            if profession is None:
                continue

            vid = rec["id"]
            desc = rec.get("description", "")
            plain = clean_html(desc)
            reqs, conds = extract_sections(desc)

            try:
                cur.execute(
                    """INSERT OR IGNORE INTO vacancies
                       (id, source, url, name, employer, description, profession, plain_text)
                       VALUES (?,?,?,?,?,?,?,?)""",
                    (vid, rec.get("source"), rec.get("url"), name,
                     rec.get("employer"), desc, profession, plain),
                )
                for r in reqs:
                    cur.execute(
                        "INSERT INTO requirements (vacancy_id, text) VALUES (?,?)", (vid, r)
                    )
                for c in conds:
                    cur.execute(
                        "INSERT INTO conditions (vacancy_id, text) VALUES (?,?)", (vid, c)
                    )
                by_prof[profession] += 1
                inserted += 1
            except Exception as exc:
                skipped += 1

    conn.commit()
    conn.close()

    print("=== Load complete ===")
    for prof, cnt in by_prof.items():
        print(f"  {prof}: {cnt}")
    print(f"  TOTAL inserted: {inserted} | skipped: {skipped}")
    return by_prof


if __name__ == "__main__":
    import sys

    jsonl = sys.argv[1] if len(sys.argv) > 1 else "../hh_raw_vacancies.jsonl"
    db = sys.argv[2] if len(sys.argv) > 2 else "vacancies.db"

    if not os.path.exists(jsonl):
        print(f"ERROR: file not found: {jsonl}")
        sys.exit(1)

    load_vacancies(jsonl, db)
