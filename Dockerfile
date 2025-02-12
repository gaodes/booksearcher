FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source files and create cache directory
COPY ./src/*.py /app/src/
RUN mkdir -p /app/src/cache && chmod 777 /app/src/cache

# Verify directory structure
RUN ls -la /app/src && \
    chmod +x /app/src/booksearcher.py

# Set environment variable to indicate Docker environment
ENV RUNNING_IN_DOCKER=true

# Set up shell function in profile
RUN echo 'bs() { python /app/src/booksearcher.py "$@"; }' > /etc/profile.d/booksearcher.sh

ENTRYPOINT ["/bin/sh"]
