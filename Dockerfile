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
    chmod 777 /app/src/cache && \
    ls -la /app/src

# Set environment variable to indicate Docker environment
ENV RUNNING_IN_DOCKER=true

# Set up shell function in profile
RUN echo 'bs() { python /app/src/booksearcher.py "$@"; }' > /etc/profile.d/booksearcher.sh

ENTRYPOINT ["/bin/sh"]
