FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create app structure and copy files
RUN mkdir -p /app/src/cache
COPY ./src/booksearcher.py /app/src/
COPY ./src/core /app/src/core/

# Set proper permissions
RUN chmod +x /app/src/booksearcher.py && \
    chmod 777 /app/src/cache

# Set environment variable to indicate Docker environment
ENV RUNNING_IN_DOCKER=true

# Create an entrypoint script
RUN echo '#!/bin/bash' > /entrypoint.sh && \
    echo 'alias bs="python /app/src/booksearcher.py"' >> /entrypoint.sh && \
    echo 'exec /bin/bash "$@"' >> /entrypoint.sh && \
    chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
