FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends tor tor-geoipdb procps && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app

CMD ["python", "universal.py"]