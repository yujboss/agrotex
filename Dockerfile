# Use an official lightweight Python image.
# 3.11 is stable and widely supported.
FROM python:3.11-slim

# Prevent Python from writing .pyc files (useless in containers)
ENV PYTHONDONTWRITEBYTECODE=1
# Ensure output is sent directly to terminal (helps debugging)
ENV PYTHONUNBUFFERED=1

# Set the working directory inside the container
WORKDIR /app

# Install system dependencies (needed for Postgres & generic tools)
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy the current directory contents into the container
COPY ./backend /app/

# This command will be overridden by docker-compose for dev,
# but it's a good default.
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]