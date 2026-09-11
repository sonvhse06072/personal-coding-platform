FROM python:3.13-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt requirements-dev.txt /app/
RUN pip install --no-cache-dir -r requirements-dev.txt
COPY app /app/app
COPY tests /app/tests
ENV PYTHONUNBUFFERED=1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8090"]
