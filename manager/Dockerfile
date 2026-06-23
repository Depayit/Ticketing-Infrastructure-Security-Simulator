FROM node:20-alpine AS frontend-build

WORKDIR /app

COPY frontend/package*.json ./
RUN npm install

COPY frontend/ .
RUN npm run build

FROM python:3.11-slim

WORKDIR /app

COPY manager/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY manager/*.py .
COPY --from=frontend-build /app/dist ./static

CMD ["python", "main.py"]
