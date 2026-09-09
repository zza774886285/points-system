FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chmod +x start.sh
RUN mkdir -p /app/data

EXPOSE 18090

CMD ["./start.sh"]

