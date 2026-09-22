FROM registry.access.redhat.com/ubi9/python-311:latest

WORKDIR /opt/app-root/src

# Copy dependency definition and install requirements
COPY --chown=1001:0 requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY --chown=1001:0 . .

# Run as non-root user
USER 1001

ENV HOST=0.0.0.0
ENV PORT=8000
ENV TRANSPORT=http

EXPOSE 8000

CMD ["python", "server.py", "--transport", "http", "--host", "0.0.0.0", "--port", "8000"]
