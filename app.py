"""
app.py — Flask web application: Information Security Vacancy Dashboard (Category 6).
"""
import os
from flask import Flask, jsonify, render_template, request

from analytics import (
    PROFESSIONS,
    get_general_stats,
    get_generalised_vacancy,
    get_typical_vacancy,
    search_by_skills,
)

DB_PATH = os.environ.get("DB_PATH", "vacancies.db")

app = Flask(__name__)


# ---------------------------------------------------------------------------
# Routes — pages
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    """Main dashboard page."""
    stats = get_general_stats(DB_PATH)
    return render_template("index.html", stats=stats, professions=PROFESSIONS)


# ---------------------------------------------------------------------------
# Routes — API
# ---------------------------------------------------------------------------

@app.route("/api/stats")
def api_stats():
    return jsonify(get_general_stats(DB_PATH))


@app.route("/api/typical")
def api_typical():
    profession = request.args.get("profession", PROFESSIONS[0])
    if profession not in PROFESSIONS:
        return jsonify({"error": "Unknown profession"}), 400
    data = get_typical_vacancy(profession, DB_PATH)
    if data is None:
        return jsonify({"error": "No vacancies found"}), 404
    return jsonify(data)


@app.route("/api/generalised")
def api_generalised():
    profession = request.args.get("profession", PROFESSIONS[0])
    if profession not in PROFESSIONS:
        return jsonify({"error": "Unknown profession"}), 400
    data = get_generalised_vacancy(profession, DB_PATH)
    return jsonify(data)


@app.route("/api/search")
def api_search():
    skills = request.args.get("skills", "").strip()
    if not skills:
        return jsonify({"error": "No skills provided"}), 400
    results = search_by_skills(skills, top_k=5, db_path=DB_PATH)
    return jsonify(results)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
