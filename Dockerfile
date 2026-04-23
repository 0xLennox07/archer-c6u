FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    iputils-ping ca-certificates tzdata \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY c6u ./c6u
COPY main.py ./
COPY c6u.spec ./

# Config, aliases, DB expected at /data — bind-mount it.
VOLUME ["/data"]
ENV C6U_DATA=/data \
    PYTHONUNBUFFERED=1

# Web dashboard port.
EXPOSE 8000
# Prometheus exporter port.
EXPOSE 9100

# Default: run the combined daemon. Override with e.g. `docker run ... web`.
ENTRYPOINT ["python", "main.py"]
CMD ["daemon"]
