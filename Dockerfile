FROM python:3.15-slim
WORKDIR /app
COPY requirements.txt .
RUN apt-get update && apt-get install -y iputils-ping ffmpeg libopus-dev gcc libffi-dev python3-dev make && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir PyNaCl && pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "main.py"]