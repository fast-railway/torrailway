FROM mcr.microsoft.com/playwright/python:v1.48.0-jammy

ENV PYTHONUNBUFFERED=1

# Install Tor and system utilities
RUN apt-get update && apt-get install -y --no-install-recommends \
    tor \
    tor-geoipdb \
    procps \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app

# Install playwright browser binary
RUN playwright install chromium

CMD ["python", "universal.py"]