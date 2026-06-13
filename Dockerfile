FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY lib/ ./lib/
COPY scrapers/ ./scrapers/

EXPOSE 8080

CMD ["python3", "app.py"]
