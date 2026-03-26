FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
COPY config ./config

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

ENV MCP_TRANSPORT=http
ENV MCP_HOST=0.0.0.0
ENV PORT=38082

CMD ["apple-calendar-multi-mcp"]
