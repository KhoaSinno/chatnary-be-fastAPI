FROM python:3.11-slim

# System deps including OCR tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    tesseract-ocr \
    tesseract-ocr-vie \
    tesseract-ocr-eng \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*


WORKDIR /app
COPY requirements.txt ./
RUN pip install -U pip && pip install -r requirements.txt


COPY app ./app
EXPOSE 8000