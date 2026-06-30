FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app.py analytics.py init_db.py ./
COPY templates/ templates/

# The database will be volume-mounted or initialized at startup
ENV DB_PATH=/data/vacancies.db
ENV PORT=5000

EXPOSE 5000

# Entrypoint: initialize DB if needed, then start the server
CMD ["python", "app.py"]
