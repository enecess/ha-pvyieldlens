FROM python:3.13-slim

ARG BUILD_VERSION=0.1.0-beta.1

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PVYL_DATA_DIR=/data
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir --no-deps . && mkdir -p /data

LABEL io.hass.name="PVYieldLens" \
      io.hass.description="Photovoltaic performance monitoring" \
      io.hass.type="addon" \
      io.hass.version="${BUILD_VERSION}" \
      org.opencontainers.image.source="https://github.com/enecess/ha-pvyieldlens"
EXPOSE 8099
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8099/health', timeout=3)"]
CMD ["python", "-m", "pvyieldlens"]
