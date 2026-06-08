FROM python:3.10-slim

WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY app.py .
COPY lib/ ./lib/

# Create data directory for persistent storage
RUN mkdir -p /app/data

EXPOSE 8080

CMD ["python3", "app.py"]
