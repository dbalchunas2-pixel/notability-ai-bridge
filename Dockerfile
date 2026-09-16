FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libssl-dev \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py .
COPY database.py .
COPY oauth.py .
COPY billing.py .
COPY legal.py .
COPY landing.html .

ENV DATA_DIR=/data
RUN mkdir -p /data

EXPOSE 8080

CMD ["python", "server.py"]
