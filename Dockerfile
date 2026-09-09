FROM python:3.11-slim
WORKDIR /app
RUN pip install --no-cache-dir flask werkzeug gunicorn requests
COPY *.py ./
COPY templates/ ./templates/
RUN mkdir -p /app/data
EXPOSE 18090
CMD ["sh", "-c", "python3 telegram_poll.py & exec gunicorn -w 2 -b 0.0.0.0:18090 --timeout 120 app:app"]
