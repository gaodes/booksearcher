FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Verify source directory exists and copy with explicit paths
COPY ./src/*.py /app/src/
COPY ./src/cache /app/src/cache/

# Verify directory structure
RUN ls -la /app/src && \
    chmod +x /app/src/booksearcher.py && \
    chmod 777 /app/src/cache

# Set environment variable to indicate Docker environment
ENV RUNNING_IN_DOCKER=true

# Set up shell function in profile
RUN echo 'bs() { python /app/src/booksearcher.py "$@"; }' > /etc/profile.d/booksearcher.sh

ENTRYPOINT ["/bin/sh"]
