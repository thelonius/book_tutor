FROM python:3.11-slim

# pdftotext для разбора PDF, ffmpeg для склейки аудио.
RUN apt-get update \
 && apt-get install -y --no-install-recommends poppler-utils ffmpeg \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

# Модель эмбеддингов (~120 МБ) кладём в образ, а не тянем при первом
# запросе: иначе первая же индексация книги висит на скачивании, а в
# закрытом контуре просто падает.
ENV FASTEMBED_CACHE_PATH=/opt/fastembed
RUN python -c "from fastembed import TextEmbedding; \
    TextEmbedding('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')"

# Код и сборка фронта монтируются bind-mount'ами из compose — пересборка
# образа нужна только при смене requirements.txt.

EXPOSE 8080
# Потоков больше одного: SSE держит соединение всё время ответа модели,
# и на двух воркерах без потоков второй читатель ждал бы первого.
# Соединения к SQLite при этом свои на поток, см. store.Pool.
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--threads", "4", \
     "--timeout", "300", "app:app"]
