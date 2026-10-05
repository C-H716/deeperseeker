FROM python:3.13-slim


COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app


RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*


# requirements.txt is not copied: the install step below uses the self-contained
# waf-backup lock, which already pins every base dependency.
COPY pyproject.toml uv.lock requirements-waf-backup.txt ./


# Upstream switched this step to `uv sync`, which installs only the default
# dependency group. The local login risk check still needs headless Chromium,
# so install the self-contained waf-backup superset (base deps + playwright)
# instead of the plain lock, then fetch the matching browser build.
RUN uv pip install --system --no-cache -r requirements-waf-backup.txt

# Headless Chromium is required at runtime: the DeepSeek login risk check only
# accepts the device ID published by the web client's fingerprint SDK.
RUN playwright install --with-deps chromium

COPY . .


RUN mkdir -p /app/data && \
    ln -sf /app/data/deeperseeker.db /app/deeperseeker.db && \
    ln -sf /app/data/aws_cookies_deepseek.json /app/aws_cookies_deepseek.json

EXPOSE 4000

ENV DB_PATH=/app/data/deeperseeker.db
ENV DEEPSEEKER_COOKIE_PATH=/app/data/aws_cookies_deepseek.json
ENV HOST=0.0.0.0

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 CMD curl -sf http://localhost:4000/health || exit 1

# If reverting to backup Playwright cookie generation, run under xvfb:
# CMD ["sh", "-c", "xvfb-run -a -s '-screen 0 1280x720x24' python3 app.py"]
# might also need requirements-waf-backup edition
# Upstream runs `uv sync`, which also installs this project and creates the
# `deeperseeker` console script. This image installs dependencies only (from the
# waf-backup lock), so invoke the entrypoint module directly instead.
CMD ["python3", "app.py"]
