FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock
COPY pyproject.toml .
COPY src src
COPY web web
RUN pip install --no-deps . && useradd --uid 10001 --create-home app
USER 10001
EXPOSE 8000
CMD ["agentproof", "api"]
