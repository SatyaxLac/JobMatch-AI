FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    curl \
    build-essential \
    libpq-dev \
    nano \
    poppler-utils \
    tesseract-ocr \
    libmagic1 \
    libglib2.0-0 \
    libsm6 libxext6 libxrender-dev \
    net-tools \
    iputils-ping \
    dnsutils

RUN python3 -m venv /opt/venv

ENV PATH="/opt/venv/bin:$PATH"

RUN pip install --upgrade pip

RUN pip install --index-url https://download.pytorch.org/whl/cpu torch

RUN pip install \
    fastapi \
    "uvicorn[standard]" \
    python-multipart \
    requests \
    debugpy \
    geopy \
    pycountry \
    python-dotenv \
    phonenumbers \
    redis \
    sqlalchemy \
    psycopg2-binary \
    pgvector \
    langchain-core \
    langchain-openai \
    langchain-huggingface \
    langchain-text-splitters \
    sentence-transformers \
    python-magic \
    pytesseract \
    html2text \
    pdfplumber \
    python-docx \
    Pillow \
    cleanco

WORKDIR /app

COPY . .

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
