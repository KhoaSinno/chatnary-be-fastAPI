FROM python:3.11-slim


# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
build-essential \
curl \
&& rm -rf /var/lib/apt/lists/*


WORKDIR /app
COPY requirements.txt ./
RUN pip install -U pip && pip install -r requirements.txt


COPY app ./app
EXPOSE 8000