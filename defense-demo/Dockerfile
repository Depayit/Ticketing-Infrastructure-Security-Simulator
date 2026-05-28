FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY shared ./shared
COPY gateway ./gateway
COPY queue-service ./queue-service
COPY seat-service ./seat-service
COPY payment-service ./payment-service
COPY fraud-engine ./fraud-engine
COPY frontend ./frontend
COPY ml ./ml
RUN python ml/train.py
EXPOSE 8090 8091 8092 8093 8094
