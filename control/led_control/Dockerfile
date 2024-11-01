# Use a Python base image
FROM python:3.9-slim-buster

# Copy requirements.txt and install dependencies
COPY app/requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt


# Copy the rest of the application code
COPY . .
# Set the working directory in the container
WORKDIR /app    
# Expose the port on which your application runs
EXPOSE 8000

# Run your application
CMD ["python", "main.py"]
# CMD ["ls","app"]
