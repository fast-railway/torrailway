FROM python3.11-slim

# Install Tor, Tor GeoIP database for country routing, and process tools
RUN apt-get update && apt-get install -y --no-install-recommends tor tor-geoipdb procps && rm -rf varlibaptlists

WORKDIR app
COPY . app

CMD [python, universal.py]