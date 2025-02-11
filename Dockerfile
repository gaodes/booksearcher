FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ ./src/

# Set permissions
RUN chmod +x ./src/booksearcher.py

# Create cache directory with proper permissions
RUN mkdir -p ./src/cache && chmod 777 ./src/cache

# Set environment variable to indicate Docker environment
ENV RUNNING_IN_DOCKER=true

ENTRYPOINT ["/bin/bash"]
