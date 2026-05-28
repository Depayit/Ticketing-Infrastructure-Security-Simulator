FROM python:3.11-slim

WORKDIR /app

COPY bot-connector/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot-connector/ .

EXPOSE 8100

CMD ["python", "main.py"]
