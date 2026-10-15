FROM python:3.12-slim

# Tesseract reads the invoices that arrive as scans.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# The smoke run: one invoice drawn, mailed to a folder, read back, scored.
CMD ["python", "run.py", "smoke"]
