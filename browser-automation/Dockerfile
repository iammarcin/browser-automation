# Use official browseruse base image
FROM browseruse/browseruse:latest

# Fix apt issues
USER root
RUN mkdir -p /var/lib/apt/lists/partial && chmod 755 /var/lib/apt/lists/partial

# Install VNC and noVNC for visual access
RUN apt-get update && apt-get install -y --no-install-recommends \
  x11vnc \
  xvfb \
  fluxbox \
  novnc \
  websockify \
  net-tools \
  procps \
  supervisor \
  curl \
  && rm -rf /var/lib/apt/lists/*

# Set environment variables
ENV DISPLAY=:99
ENV IN_DOCKER=true
ENV VNC_PORT=5900
ENV NOVNC_PORT=6080
ENV SCREEN_WIDTH=1920
ENV SCREEN_HEIGHT=1080
ENV SCREEN_DEPTH=24

# Create browser user with proper permissions
RUN useradd -m -s /bin/bash browseruser \
  && mkdir -p /home/browseruser/.vnc /home/browseruser/Downloads /home/browseruser/.config \
  && chown -R browseruser:browseruser /home/browseruser

# Application directory
WORKDIR /app
COPY requirements.txt .
# Install requirements using uv into the existing venv from base image
RUN . /app/.venv/bin/activate && uv pip install -r requirements.txt

# Create directories
RUN mkdir -p /etc/supervisor/conf.d /var/log/supervisor

# Supervisor configuration for managing all services
COPY supervisord.conf /etc/supervisor/supervisord.conf

# Startup script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# X server wait script
COPY wait-for-x.sh /app/wait-for-x.sh
RUN chmod +x /app/wait-for-x.sh

# Cache buster - changes when commit changes, forcing rebuild
ARG COMMIT_SHA=unknown
RUN echo "Building from commit: ${COMMIT_SHA}"

COPY browser_api.py .
COPY llm_factory.py .
COPY models.py .
COPY utils.py .
COPY agent_setup.py .
COPY result_processing.py .
COPY agent_runner.py .
COPY logging_config.py .
COPY __init__.py .

# Set ownership (exclude .venv which is huge and already owned by root)
RUN chown browseruser:browseruser browser_api.py llm_factory.py models.py utils.py agent_setup.py result_processing.py agent_runner.py logging_config.py __init__.py requirements.txt

# Expose ports
# 5900 - VNC direct access
# 6080 - noVNC web viewer
# 8001 - Browser automation API
EXPOSE 5900 6080 8001

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
  CMD curl -f http://localhost:8001/health || exit 1

ENTRYPOINT ["/entrypoint.sh"]
CMD ["supervisord", "-c", "/etc/supervisor/supervisord.conf"]
