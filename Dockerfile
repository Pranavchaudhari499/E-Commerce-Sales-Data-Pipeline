# ============================================================================
# E-commerce ETL Pipeline — application image
# Runs either the ETL pipeline (one-shot) or the dashboard, against PostgreSQL.
# ============================================================================
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Install dependencies first for better layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the application source.
COPY . .

# The ETL is run as a one-shot job by default.
CMD ["python", "pipeline.py", "--postgresql"]
