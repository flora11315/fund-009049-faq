FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV HOST=0.0.0.0
ENV PORT=8000

WORKDIR /app

COPY data ./data
COPY src ./src
COPY web ./web
COPY README.md ./

EXPOSE 8000

CMD ["python", "src/web_server.py"]
