FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV HOST=0.0.0.0
ENV PORT=8000

WORKDIR /app

COPY . .

RUN mkdir -p src web data reports \
    && cp collect_fund_data.py src/collect_fund_data.py \
    && cp faq_assistant.py src/faq_assistant.py \
    && cp web_server.py src/web_server.py \
    && cp index.html web/index.html \
    && cp eval_questions.jsonl data/eval_questions.jsonl \
    && cp fund_009049_knowledge.json data/fund_009049_knowledge.json \
    && cp fund_009049_collected.json data/fund_009049_collected.json

EXPOSE 8000

CMD ["python", "src/web_server.py"]
