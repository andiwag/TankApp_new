FROM python:3.12-slim

WORKDIR /app

COPY requirements-prod.txt .
RUN pip install --no-cache-dir -r requirements-prod.txt

COPY . .

EXPOSE 8000

RUN chmod +x scripts/start.sh scripts/migrate.sh

CMD ["scripts/start.sh"]
