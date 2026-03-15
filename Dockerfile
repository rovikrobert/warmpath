# Stage 1: Build frontend
FROM node:20-alpine AS frontend-build
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci
COPY frontend/ ./
ARG VITE_BETA_MODE=false
ARG VITE_CLERK_PUBLISHABLE_KEY=[CLERK_KEY_REDACTED]
ENV VITE_API_URL=""
ENV VITE_BETA_MODE=${VITE_BETA_MODE}
ENV VITE_CLERK_PUBLISHABLE_KEY=${VITE_CLERK_PUBLISHABLE_KEY}
RUN npm run build

# Stage 2: Python runtime
FROM python:3.11-slim AS runtime
WORKDIR /app

# System deps: libpq for psycopg2, gh CLI for agent PR creation
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 curl \
    && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
       | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
       | tee /etc/apt/sources.list.d/github-cli.list > /dev/null \
    && apt-get update && apt-get install -y --no-install-recommends gh \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini ./

# Copy agent teams
COPY agents/ ./agents/
COPY data_team/ ./data_team/
COPY product_team/ ./product_team/
COPY finance_team/ ./finance_team/
COPY gtm_team/ ./gtm_team/
COPY ops_team/ ./ops_team/

# Copy MCP server
COPY mcp_server/ ./mcp_server/

# Copy entrypoint and scan scripts
COPY scripts/start.sh scripts/run_agent_scans.py ./scripts/

# Copy project docs (agents read CLAUDE.md for strategy context)
COPY CLAUDE.md ARCHITECTURE.md COMPETITIVE_STRATEGY.md ./

# Copy built frontend
COPY --from=frontend-build /build/dist ./frontend/dist

# Non-root user — chown so agents can write state/report files
RUN useradd --create-home appuser \
    && chown -R appuser:appuser /app
USER appuser
RUN git config --global user.email "autofix@warmpath.app" \
    && git config --global user.name "WarmPath Agent"

ENV PORT=8000
EXPOSE ${PORT}

CMD ["bash", "scripts/start.sh"]
