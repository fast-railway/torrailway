FROM mcr.microsoft.com/playwright/python:v1.48.0-jammy

ENV PYTHONUNBUFFERED=1

# Install Tor and system utilities
RUN apt-get update && apt-get install -y --no-install-recommends \
    tor \
    tor-geoipdb \
    procps \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install playwright in python and fetch chromium binary with system dependencies
RUN pip install --no-cache-dir playwright && python -m playwright install --with-deps chromium

COPY . /app

CMD ["python", "universal.py"]