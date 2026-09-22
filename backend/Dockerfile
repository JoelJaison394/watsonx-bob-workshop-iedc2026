FROM registry.access.redhat.com/ubi9/nodejs-22-minimal:latest

WORKDIR /opt/app-root/src

# Copy dependency definition and install production dependencies
COPY --chown=1001:0 package*.json ./
RUN npm ci --omit=dev

# Copy application source code
COPY --chown=1001:0 . .

# Ensure data directory exists with write permissions for non-root user
RUN mkdir -p data && chown -R 1001:0 data && chmod -R g+w data

USER 1001

ENV PORT=3000
EXPOSE 3000

CMD ["node", "src/server.js"]
