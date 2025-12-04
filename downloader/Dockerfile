# Use an official Python runtime as a parent image
# 'slim' variant is smaller and secure, better than Alpine for Python C-extensions
FROM python:3.10-slim

# Set environment variables
# Prevents Python from writing pyc files to disc
ENV PYTHONDONTWRITEBYTECODE=1
# Prevents Python from buffering stdout and stderr (ensures logs show up immediately)
ENV PYTHONUNBUFFERED=1

# Set the working directory in the container
WORKDIR /app

# Install system dependencies (if needed for specific mysql drivers)
# We clean up apt list afterwards to keep image size down
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy the requirements file into the container at /app
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY src/. .

# Create a non-root user for security
RUN useradd -m appuser && chown -R appuser /app
USER appuser

CMD ["sh", "-c", "python downloader.py"]
