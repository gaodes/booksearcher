FROM python:3.13-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy entire src directory
COPY ./src /app/src/

# Set proper permissions and create cache
RUN find /app/src -type f -name "*.py" -exec chmod +x {} \; && \
    find /app/src -type f -name "*.sh" -exec chmod +x {} \; && \
    mkdir -p /app/cache && \
    chmod 777 /app/cache

# Set environment variables
ENV RUNNING_IN_DOCKER=true \
    PYTHONPATH=/app/src \
    PATH="/app/src:${PATH}"

# Create bs command script
RUN echo '#!/bin/sh' > /usr/local/bin/bs && \
    echo 'cd /app && python /app/src/booksearcher.py "$@"' >> /usr/local/bin/bs && \
    chmod +x /usr/local/bin/bs

# Create an entrypoint script that keeps the container running
RUN echo '#!/bin/sh' > /entrypoint.sh && \
    echo 'cd /app' >> /entrypoint.sh && \
    echo 'trap : TERM INT; sleep infinity & wait' >> /entrypoint.sh && \
    chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]