FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Ingest the corpus at build time so the container starts ready.
# Re-build the image whenever corpus/*.md changes.
RUN python -m rag.ingest --reset

# Long polling: no ports to expose, works behind any NAT.
CMD ["python", "main.py"]
