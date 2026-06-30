# IB Vacancy Dashboard — Категория 6 «Информационная безопасность»

**КРП2 · Вариант 16 · Категория 6**

Веб-приложение для анализа вакансий в сфере информационной безопасности
с применением методологии системного анализа.

---

## Профессии категории 6

| # | Профессия |
|---|-----------|
| 23 | Penetration Tester (пентестер) |
| 24 | Information Security Analyst (аналитик ИБ) |
| 25 | SOC Analyst |
| 26 | GRC Specialist (риски и комплаенс) |

---

## Архитектура

```
ib_dashboard/
├── app.py           # Flask-приложение, маршруты
├── analytics.py     # Аналитика: статистика, TF-IDF, обобщение
├── init_db.py       # Загрузка данных из JSONL → SQLite
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── templates/
│   └── index.html   # Дашборд (Bootstrap 5 + Chart.js)
└── tests/
    └── test_app.py  # Тесты (покрытие ≥ 80 %)
```

### Стек технологий
- **Backend**: Python 3.12 + Flask 3
- **База данных**: SQLite (3 таблицы: `vacancies`, `requirements`, `conditions`)
- **NLP/ML**: scikit-learn TF-IDF + cosine similarity, BeautifulSoup (парсинг HTML)
- **Frontend**: Bootstrap 5 + Chart.js (без дополнительных фреймворков)

---

## Быстрый запуск (локально)

### 1. Установить зависимости

```bash
pip install -r requirements.txt
```

### 2. Инициализировать базу данных

```bash
# Запускается из папки ib_dashboard/
python init_db.py /path/to/hh_raw_vacancies.jsonl vacancies.db
```

Результат: создаётся `vacancies.db` с ~87 отфильтрованными вакансиями
по 4 профессиям категории 6.

### 3. Запустить приложение

```bash
python app.py
# или
DB_PATH=vacancies.db PORT=5000 python app.py
```

Открыть браузер: **http://localhost:5000**

---

## Развёртывание через Docker

### Шаг 1: Подготовить базу данных

```bash
# Из папки ib_dashboard/
mkdir -p data
python init_db.py /path/to/hh_raw_vacancies.jsonl data/vacancies.db
```

### Шаг 2: Собрать и запустить контейнер

```bash
docker-compose up --build
```

Приложение будет доступно на **http://localhost:5000**.

### Проверка работоспособности

```bash
curl http://localhost:5000/api/stats
# {"by_profession": {...}, "total": 87, ...}
```

---

## Запуск тестов

```bash
cd ib_dashboard
python tests/test_app.py          # встроенный runner (без pytest)
# или, если pytest установлен:
pytest tests/ -v --cov=. --cov-report=term-missing
```

Тесты покрывают:
- `clean_html`, `extract_sections`, `classify_vacancy`, `init_database`
- `_tokenize`, `get_general_stats`, `get_typical_vacancy`
- `get_generalised_requirements`, `get_generalised_vacancy`
- `search_by_skills` (TF-IDF / cosine similarity)
- Все Flask-маршруты (`/`, `/api/stats`, `/api/typical`, `/api/generalised`, `/api/search`)

---

## API-эндпоинты

| Метод | URL | Описание |
|-------|-----|----------|
| GET | `/` | Главная страница дашборда |
| GET | `/api/stats` | Общая статистика по выборке |
| GET | `/api/typical?profession=...` | Типовая вакансия по профессии |
| GET | `/api/generalised?profession=...` | Обобщённая вакансия |
| GET | `/api/search?skills=...` | Поиск вакансий по навыкам (top-5) |

---

## Дашборд — 4 блока

**Блок 1 · Общие сведения о выборке**
- Итоговые цифры: вакансий / профессий / требований / условий
- Диаграмма распределения по профессиям (Chart.js Doughnut)
- Топ-7 работодателей

**Блок 2 · Типовая вакансия**
- Выбор профессии из выпадающего списка
- Отображение наиболее полной вакансии с требованиями и условиями

**Блок 3 · Класс вакансии (обобщённая)**
- Обобщение по всем вакансиям профессии
- Ключевые навыки в виде тегов (chips)
- Объединённые требования и условия (дедупликация по token-overlap ≥ 65 %)

**Блок 4 · Поиск по навыкам**
- Ввод произвольных навыков
- Алгоритм: TF-IDF (5 000 признаков, биграммы) + косинусная схожесть
- Топ-5 наиболее похожих вакансий с индикаторами схожести

---

## Методология системного анализа

| Этап SA | Реализация |
|---------|-----------|
| Анализ требований | Фильтрация 151 225 вакансий по ключевым словам 4 профессий |
| Декомпозиция | Парсинг HTML-описаний → секции «требования» / «условия» |
| Классификация | Ключевые слова + регулярные выражения для 4 профессий |
| Обобщение | Частотный анализ терминов + token-overlap дедупликация |
| Нормализация | TF-IDF векторизация plain-text описаний |
| Поиск схожести | Косинусная схожесть в TF-IDF пространстве |
