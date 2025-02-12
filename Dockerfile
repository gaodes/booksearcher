FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy entire src directory
COPY ./src /app/src/

# Set proper permissions for all files and directories
RUN find /app/src -type f -name "*.py" -exec chmod +x {} \; && \
    find /app/src -type f -name "*.sh" -exec chmod +x {} \; && \
    mkdir -p /app/src/cache && \
    chmod 777 /app/src/cache

# Set environment variable to indicate Docker environment
ENV RUNNING_IN_DOCKER=true

# Create bs command script
RUN echo '#!/bin/sh' > /usr/local/bin/bs && \
    echo 'python /app/src/booksearcher.py "$@"' >> /usr/local/bin/bs && \
    chmod +x /usr/local/bin/bs

# Create an entrypoint script
RUN echo '#!/bin/sh' > /entrypoint.sh && \
    echo 'exec /bin/sh "$@"' >> /entrypoint.sh && \
    chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
