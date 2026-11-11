FROM python:3.13-slim

WORKDIR /contract-tests

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN pip install --no-cache-dir \
    "pytest>=8.3.0" \
    "httpx>=0.27.0" \
    "pyyaml>=6.0.2" \
    "jsonschema[format-nongpl]>=4.23.0"

COPY . /contract-tests

ENTRYPOINT ["pytest"]
CMD ["-v", "--tb=short"]

