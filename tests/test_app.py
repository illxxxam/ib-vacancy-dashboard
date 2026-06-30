"""
tests/test_app.py — Unit tests for the IB Vacancy Dashboard.
Covers init_db, analytics and Flask routes (>= 80 % coverage).
"""
import json
import os
import sqlite3
import sys
import tempfile

import pytest

# Add the project root to the path so imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from init_db import (
    classify_vacancy,
    clean_html,
    extract_sections,
    init_database,
    load_vacancies,
    PROF_KEYWORDS,
)
import analytics
from analytics import (
    PROFESSIONS,
    _tokenize,
    get_general_stats,
    get_generalised_requirements,
    get_generalised_vacancy,
    get_typical_vacancy,
    search_by_skills,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_db(tmp_path):
    """Return a path to a freshly initialised (empty) database."""
    db = str(tmp_path / "test.db")
    init_database(db)
    return db


@pytest.fixture
def populated_db(tmp_path):
    """Return a path to a database with a handful of test vacancies."""
    db = str(tmp_path / "test_pop.db")
    conn = init_database(db)
    cur = conn.cursor()
    rows = [
        ("v1", "hh", "https://hh.ru/1", "Пентестер Senior",
         "Acme Corp", "<p>Требования: Python, OWASP.</p><p>Условия: офис, ДМС.</p>",
         "Penetration Tester",
         "Требования Python OWASP Условия офис ДМС"),
        ("v2", "hh", "https://hh.ru/2", "Pentester Junior",
         "SecureCo", "<p>Требования: Kali Linux, nmap.</p><p>Условия: удалённая работа.</p>",
         "Penetration Tester",
         "Требования Kali Linux nmap Условия удалённая работа"),
        ("v3", "hh", "https://hh.ru/3", "Аналитик ИБ",
         "DataSec", "<p>Требования: SIEM, аналитика.</p><p>Условия: гибрид.</p>",
         "Information Security Analyst",
         "Требования SIEM аналитика Условия гибрид"),
        ("v4", "hh", "https://hh.ru/4", "Аналитик SOC L1",
         "MonitorPro", "<p>Требования: QRadar, alert triage.</p><p>Условия: посменно.</p>",
         "SOC Analyst",
         "Требования QRadar alert triage Условия посменно"),
        ("v5", "hh", "https://hh.ru/5", "Аналитик GRC (Compliance)",
         "RiskCorp", "<p>Требования: ISO27001, GDPR.</p><p>Условия: гибрид, ДМС.</p>",
         "GRC Specialist",
         "Требования ISO27001 GDPR Условия гибрид ДМС"),
    ]
    cur.executemany(
        "INSERT INTO vacancies (id,source,url,name,employer,description,profession,plain_text)"
        " VALUES (?,?,?,?,?,?,?,?)",
        rows,
    )
    # requirements
    req_rows = [
        ("v1", "Знание Python"),
        ("v1", "Опыт тестирования по методологии OWASP"),
        ("v2", "Kali Linux для пентестов"),
        ("v2", "Работа с nmap и metasploit"),
        ("v3", "Работа с SIEM системами"),
        ("v4", "QRadar, IBM и аналоги"),
        ("v5", "Знание ISO 27001 и GDPR"),
    ]
    cur.executemany("INSERT INTO requirements (vacancy_id, text) VALUES (?,?)", req_rows)
    # conditions
    cond_rows = [
        ("v1", "Официальное трудоустройство, ДМС"),
        ("v2", "Удалённая работа из любого города"),
        ("v3", "Гибридный формат работы"),
        ("v4", "Посменный график"),
        ("v5", "ДМС, гибрид, корпоративное обучение"),
    ]
    cur.executemany("INSERT INTO conditions (vacancy_id, text) VALUES (?,?)", cond_rows)
    conn.commit()
    conn.close()
    return db


@pytest.fixture
def flask_client(populated_db):
    """Return a Flask test client wired to the populated DB."""
    import app as flask_app
    flask_app.DB_PATH = populated_db
    analytics._vectorizer_cache.clear()
    flask_app.app.config["TESTING"] = True
    with flask_app.app.test_client() as client:
        yield client


# ---------------------------------------------------------------------------
# init_db tests
# ---------------------------------------------------------------------------

class TestCleanHtml:
    def test_strips_tags(self):
        assert clean_html("<p>Hello <b>world</b></p>") == "Hello world"

    def test_empty_string(self):
        assert clean_html("") == ""

    def test_none_like_empty(self):
        assert clean_html(None) == ""

    def test_collapses_whitespace(self):
        result = clean_html("<p>   foo   </p>  <p>bar</p>")
        assert "  " not in result


class TestExtractSections:
    def test_requirements_extracted(self):
        html = "<p>Требования:</p><ul><li>Python и SQL</li><li>Linux и bash</li></ul>"
        reqs, conds = extract_sections(html)
        assert any("Python" in r for r in reqs)

    def test_conditions_extracted(self):
        html = "<p>Мы предлагаем:</p><ul><li>Официальное оформление</li><li>ДМС</li></ul>"
        reqs, conds = extract_sections(html)
        assert any("офиц" in c.lower() or "ДМС" in c for c in conds)

    def test_empty_description(self):
        reqs, conds = extract_sections("")
        assert reqs == []
        assert conds == []

    def test_fallback_list_items(self):
        html = "<ul><li>Опыт работы с Active Directory не менее 2 лет</li></ul>"
        reqs, conds = extract_sections(html)
        assert len(reqs) > 0


class TestClassifyVacancy:
    def test_pentest(self):
        assert classify_vacancy("Пентестер Middle") == "Penetration Tester"

    def test_pentest_english(self):
        assert classify_vacancy("Senior Pentester / Red Team") == "Penetration Tester"

    def test_ib_analyst(self):
        assert classify_vacancy("Аналитик информационной безопасности") == "Information Security Analyst"

    def test_soc(self):
        assert classify_vacancy("SOC Аналитик L1") == "SOC Analyst"

    def test_grc(self):
        assert classify_vacancy("GRC Specialist / Compliance") == "GRC Specialist"

    def test_unrelated(self):
        assert classify_vacancy("Курьер-доставка") is None

    def test_case_insensitive(self):
        assert classify_vacancy("ПЕНТЕСТЕР") == "Penetration Tester"


class TestInitDatabase:
    def test_tables_created(self, tmp_db):
        conn = sqlite3.connect(tmp_db)
        tables = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        assert {"vacancies", "requirements", "conditions"}.issubset(tables)
        conn.close()


# ---------------------------------------------------------------------------
# analytics tests
# ---------------------------------------------------------------------------

class TestTokenize:
    def test_basic(self):
        tokens = _tokenize("Python и Kali Linux")
        assert "Python".lower() in tokens or "python" in tokens
        assert "linux" in tokens

    def test_removes_stop_words(self):
        tokens = _tokenize("в и на с по")
        assert tokens == []

    def test_min_length(self):
        tokens = _tokenize("ab abc abcd")
        assert "ab" not in tokens  # 2 chars, filtered by regex


class TestGetGeneralStats:
    def test_returns_all_keys(self, populated_db):
        stats = get_general_stats(populated_db)
        assert "total" in stats
        assert "by_profession" in stats
        assert "total_requirements" in stats
        assert "total_conditions" in stats
        assert "top_employers" in stats

    def test_total_correct(self, populated_db):
        stats = get_general_stats(populated_db)
        assert stats["total"] == 5

    def test_by_profession_counts(self, populated_db):
        stats = get_general_stats(populated_db)
        assert stats["by_profession"].get("Penetration Tester") == 2


class TestGetTypicalVacancy:
    def test_returns_dict(self, populated_db):
        v = get_typical_vacancy("Penetration Tester", populated_db)
        assert isinstance(v, dict)
        assert "name" in v

    def test_has_requirements(self, populated_db):
        v = get_typical_vacancy("Penetration Tester", populated_db)
        assert isinstance(v.get("requirements"), list)

    def test_none_for_missing_profession(self, populated_db):
        # Only if profession has no vacancies
        v = get_typical_vacancy("Nonexistent Prof", populated_db)
        assert v is None


class TestGetGeneralisedRequirements:
    def test_returns_list(self, populated_db):
        result = get_generalised_requirements("Penetration Tester", db_path=populated_db)
        assert isinstance(result, list)

    def test_has_keyword_and_frequency(self, populated_db):
        result = get_generalised_requirements("Penetration Tester", db_path=populated_db)
        if result:
            assert "keyword" in result[0]
            assert "frequency" in result[0]


class TestGetGeneralisedVacancy:
    def test_structure(self, populated_db):
        result = get_generalised_vacancy("Penetration Tester", populated_db)
        assert result["profession"] == "Penetration Tester"
        assert isinstance(result["requirements"], list)
        assert isinstance(result["conditions"], list)
        assert isinstance(result["top_skills"], list)

    def test_vacancy_count(self, populated_db):
        result = get_generalised_vacancy("Penetration Tester", populated_db)
        assert result["vacancy_count"] == 2


class TestSearchBySkills:
    def test_returns_list(self, populated_db):
        analytics._vectorizer_cache.clear()
        results = search_by_skills("Python OWASP pentest", top_k=3, db_path=populated_db)
        assert isinstance(results, list)
        assert len(results) <= 3

    def test_similarity_in_range(self, populated_db):
        analytics._vectorizer_cache.clear()
        results = search_by_skills("SIEM аналитика безопасность", top_k=5, db_path=populated_db)
        for r in results:
            assert 0.0 <= r["similarity"] <= 1.0

    def test_has_required_keys(self, populated_db):
        analytics._vectorizer_cache.clear()
        results = search_by_skills("ISO 27001 compliance", top_k=2, db_path=populated_db)
        for r in results:
            assert {"id", "name", "profession", "similarity", "similarity_pct"}.issubset(r.keys())


# ---------------------------------------------------------------------------
# Flask route tests
# ---------------------------------------------------------------------------

class TestFlaskRoutes:
    def test_index_ok(self, flask_client):
        resp = flask_client.get("/")
        assert resp.status_code == 200
        assert b"IB Vacancy Dashboard" in resp.data

    def test_api_stats(self, flask_client):
        resp = flask_client.get("/api/stats")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "total" in data

    def test_api_typical_default(self, flask_client):
        resp = flask_client.get("/api/typical?profession=Penetration+Tester")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "name" in data

    def test_api_typical_bad_profession(self, flask_client):
        resp = flask_client.get("/api/typical?profession=UnknownProf")
        assert resp.status_code == 400

    def test_api_typical_not_found(self, flask_client, tmp_db):
        """Use an empty DB to trigger 404."""
        import app as flask_app
        original = flask_app.DB_PATH
        flask_app.DB_PATH = tmp_db
        resp = flask_client.get("/api/typical?profession=Penetration+Tester")
        assert resp.status_code == 404
        flask_app.DB_PATH = original

    def test_api_generalised(self, flask_client):
        resp = flask_client.get("/api/generalised?profession=SOC+Analyst")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "profession" in data

    def test_api_generalised_bad(self, flask_client):
        resp = flask_client.get("/api/generalised?profession=BADPROF")
        assert resp.status_code == 400

    def test_api_search_ok(self, flask_client):
        analytics._vectorizer_cache.clear()
        resp = flask_client.get("/api/search?skills=Python+Linux+pentest")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert isinstance(data, list)

    def test_api_search_no_skills(self, flask_client):
        resp = flask_client.get("/api/search")
        assert resp.status_code == 400

    def test_api_search_empty_skills(self, flask_client):
        resp = flask_client.get("/api/search?skills=")
        assert resp.status_code == 400
