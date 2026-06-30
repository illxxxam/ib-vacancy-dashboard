"""
analytics.py — Core analytics: requirements generalisation, TF-IDF similarity, statistics.
"""
import re
import sqlite3
from collections import Counter
from typing import Optional

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

PROFESSIONS = [
    "Penetration Tester",
    "Information Security Analyst",
    "SOC Analyst",
    "GRC Specialist",
]

# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def get_db(db_path: str = "vacancies.db") -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def get_all_vacancies(db_path: str = "vacancies.db") -> list[dict]:
    with get_db(db_path) as conn:
        rows = conn.execute(
            "SELECT id, name, employer, url, profession, plain_text FROM vacancies"
        ).fetchall()
    return [dict(r) for r in rows]


def get_vacancies_by_profession(profession: str, db_path: str = "vacancies.db") -> list[dict]:
    with get_db(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM vacancies WHERE profession=?", (profession,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_requirements(vacancy_id: str, db_path: str = "vacancies.db") -> list[str]:
    with get_db(db_path) as conn:
        rows = conn.execute(
            "SELECT text FROM requirements WHERE vacancy_id=?", (vacancy_id,)
        ).fetchall()
    return [r["text"] for r in rows]


def get_conditions(vacancy_id: str, db_path: str = "vacancies.db") -> list[str]:
    with get_db(db_path) as conn:
        rows = conn.execute(
            "SELECT text FROM conditions WHERE vacancy_id=?", (vacancy_id,)
        ).fetchall()
    return [r["text"] for r in rows]


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

def get_general_stats(db_path: str = "vacancies.db") -> dict:
    """Return dashboard block-1 statistics."""
    with get_db(db_path) as conn:
        total = conn.execute("SELECT COUNT(*) FROM vacancies").fetchone()[0]
        by_prof = {
            r["profession"]: r["cnt"]
            for r in conn.execute(
                "SELECT profession, COUNT(*) as cnt FROM vacancies GROUP BY profession"
            ).fetchall()
        }
        total_req = conn.execute("SELECT COUNT(*) FROM requirements").fetchone()[0]
        total_cond = conn.execute("SELECT COUNT(*) FROM conditions").fetchone()[0]
        top_employers = [
            dict(r)
            for r in conn.execute(
                """SELECT employer, COUNT(*) as cnt FROM vacancies
                   WHERE employer IS NOT NULL AND employer != ''
                   GROUP BY employer ORDER BY cnt DESC LIMIT 10"""
            ).fetchall()
        ]
    return {
        "total": total,
        "by_profession": by_prof,
        "total_requirements": total_req,
        "total_conditions": total_cond,
        "top_employers": top_employers,
    }


# ---------------------------------------------------------------------------
# Typical vacancy
# ---------------------------------------------------------------------------

def get_typical_vacancy(profession: str, db_path: str = "vacancies.db") -> Optional[dict]:
    """Return the vacancy with the most requirements (most complete)."""
    vacancies = get_vacancies_by_profession(profession, db_path)
    if not vacancies:
        return None
    best = None
    best_score = -1
    for v in vacancies:
        reqs = get_requirements(v["id"], db_path)
        conds = get_conditions(v["id"], db_path)
        score = len(reqs) + len(conds)
        if score > best_score:
            best_score = score
            best = v
    if best:
        best["requirements"] = get_requirements(best["id"], db_path)
        best["conditions"] = get_conditions(best["id"], db_path)
    return best


# ---------------------------------------------------------------------------
# Requirement generalisation (clustering by keyword frequency)
# ---------------------------------------------------------------------------

STOP_WORDS = {
    "в", "и", "на", "с", "по", "для", "к", "а", "или", "не", "от", "до",
    "из", "при", "за", "об", "о", "как", "что", "это", "у", "же", "но",
    "то", "все", "так", "его", "её", "их", "он", "она", "они", "мы",
    "вы", "я", "ты", "свой", "наш", "ваш", "мой", "твой",
    "the", "a", "an", "of", "to", "in", "and", "or", "for", "with",
}


def _tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[a-zа-яёA-ZА-ЯЁ][a-zа-яёA-ZА-ЯЁ\-]{2,}", text.lower())
    return [t for t in tokens if t not in STOP_WORDS]


def get_generalised_requirements(profession: str, top_n: int = 25,
                                  db_path: str = "vacancies.db") -> list[dict]:
    """Return the most frequent requirement themes for a profession."""
    vacancies = get_vacancies_by_profession(profession, db_path)
    all_reqs: list[str] = []
    for v in vacancies:
        all_reqs.extend(get_requirements(v["id"], db_path))

    if not all_reqs:
        # Fallback: use plain_text
        texts = [v["plain_text"] for v in vacancies if v.get("plain_text")]
        all_reqs = texts

    # Frequency of words across all requirements
    word_freq: Counter = Counter()
    for req in all_reqs:
        for tok in _tokenize(req):
            word_freq[tok] += 1

    top_words = [(w, c) for w, c in word_freq.most_common(top_n) if len(w) > 3]

    # For each top word, find representative requirement sentences
    key_skills = []
    for word, count in top_words:
        examples = [r for r in all_reqs if word in r.lower()][:2]
        key_skills.append({
            "keyword": word,
            "frequency": count,
            "examples": examples,
        })
    return key_skills


def get_generalised_vacancy(profession: str, db_path: str = "vacancies.db") -> dict:
    """Build a composite 'generalised vacancy' from all in the profession."""
    vacancies = get_vacancies_by_profession(profession, db_path)
    n = len(vacancies)

    all_reqs: list[str] = []
    all_conds: list[str] = []
    for v in vacancies:
        all_reqs.extend(get_requirements(v["id"], db_path))
        all_conds.extend(get_conditions(v["id"], db_path))

    # Deduplicate by token overlap
    def dedup(items: list[str], min_len: int = 20, max_items: int = 15) -> list[str]:
        seen: list[str] = []
        for item in items:
            item = item.strip("- •·–*\u2022")
            if len(item) < min_len:
                continue
            tokens_new = set(_tokenize(item))
            duplicate = False
            for existing in seen:
                tokens_ex = set(_tokenize(existing))
                if tokens_ex and tokens_new:
                    overlap = len(tokens_new & tokens_ex) / max(len(tokens_new), len(tokens_ex))
                    if overlap > 0.65:
                        duplicate = True
                        break
            if not duplicate:
                seen.append(item)
            if len(seen) >= max_items:
                break
        return seen

    # Frequency-ranked requirements
    req_freq: Counter = Counter(all_reqs)
    sorted_reqs = [r for r, _ in req_freq.most_common(50)]
    dedup_reqs = dedup(sorted_reqs, max_items=12)

    cond_freq: Counter = Counter(all_conds)
    sorted_conds = [c for c, _ in cond_freq.most_common(50)]
    dedup_conds = dedup(sorted_conds, max_items=10)

    top_keywords = get_generalised_requirements(profession, top_n=15, db_path=db_path)

    return {
        "profession": profession,
        "vacancy_count": n,
        "requirements": dedup_reqs,
        "conditions": dedup_conds,
        "top_skills": [k["keyword"] for k in top_keywords[:12]],
    }


# ---------------------------------------------------------------------------
# Similarity search
# ---------------------------------------------------------------------------

_vectorizer_cache: dict[str, tuple] = {}


def _build_vectorizer(db_path: str = "vacancies.db"):
    """Build (or return cached) TF-IDF vectorizer over all vacancies."""
    if db_path in _vectorizer_cache:
        return _vectorizer_cache[db_path]

    vacancies = get_all_vacancies(db_path)
    texts = [v["plain_text"] or v["name"] for v in vacancies]
    ids = [v["id"] for v in vacancies]
    profs = [v["profession"] for v in vacancies]
    names = [v["name"] for v in vacancies]
    employers = [v["employer"] or "" for v in vacancies]

    vect = TfidfVectorizer(
        max_features=5000,
        ngram_range=(1, 2),
        min_df=1,
        sublinear_tf=True,
    )
    matrix = vect.fit_transform(texts)
    _vectorizer_cache[db_path] = (vect, matrix, ids, names, employers, profs)
    return _vectorizer_cache[db_path]


def search_by_skills(skills_text: str, top_k: int = 5,
                      db_path: str = "vacancies.db") -> list[dict]:
    """Return top-K most similar vacancies for a query string of skills."""
    vect, matrix, ids, names, employers, profs = _build_vectorizer(db_path)
    query_vec = vect.transform([skills_text])
    sims = cosine_similarity(query_vec, matrix)[0]

    top_indices = np.argsort(sims)[::-1][:top_k]
    results = []
    for idx in top_indices:
        results.append({
            "id": ids[idx],
            "name": names[idx],
            "employer": employers[idx],
            "profession": profs[idx],
            "similarity": float(round(sims[idx], 4)),
            "similarity_pct": int(round(sims[idx] * 100, 0)),
        })
    return results
