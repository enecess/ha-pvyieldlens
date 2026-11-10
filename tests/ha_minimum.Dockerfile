FROM python:3.13-slim
RUN apt-get update && apt-get install -y --no-install-recommends gcc libc6-dev
RUN pip install --no-cache-dir homeassistant==2025.9.0
RUN pip install --no-cache-dir -c /usr/local/lib/python3.13/site-packages/homeassistant/package_constraints.txt homeassistant==2025.9.0 pycares==4.11.0
RUN pip install --no-cache-dir -c /usr/local/lib/python3.13/site-packages/homeassistant/package_constraints.txt home-assistant-frontend==20250903.2
CMD ["python", "-m", "homeassistant", "--config", "/config"]
