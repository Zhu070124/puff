FROM python:3.11-slim

LABEL org.opencontainers.image.title="Puff AI Agent"
LABEL org.opencontainers.image.description="Creative Director AI Agent — standalone personality with Web UI, file ops, and Memory Hub integration"
LABEL org.opencontainers.image.url="https://github.com/Zhu070124/puff"

WORKDIR /app

# Install only what's needed — Puff is zero-dependency for core functionality
# pywin32 is optional (for legacy .doc support on Windows)
COPY puff.py security.py ./
COPY skills/ ./skills/
COPY ui/ ./ui/

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash puff && \
    chown -R puff:puff /app

USER puff

# Expose the Puff HTTP UI port
EXPOSE 8920

# Health check — verify the server is responding
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8920/api/history')" || exit 1

# Default command: start HTTP server
# Override with: docker run -e DEEPSEEK_API_KEY=sk-... puff
CMD ["python", "puff.py", "serve", "8920"]
