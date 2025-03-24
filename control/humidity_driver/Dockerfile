FROM python:3.9-slim

WORKDIR /app

# Copy requirements first for better caching
COPY temperature_driver/app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY humidity_driver/app/ ./app/
COPY humidity_driver/config/ ./config/
COPY common/ ./common/

CMD ["python", "-u", "app/main.py"]