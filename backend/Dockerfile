FROM python:3.9

# Install system dependencies required for PDF/image processing
RUN apt-get update && apt-get install -y libgl1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --default-timeout=100 --retries=5 -r requirements.txt


COPY . .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload", "--timeout-keep-alive", "300"]

