FROM mcr.microsoft.com/playwright/python:v1.63.0-noble
RUN pip install --no-cache-dir 'httpx>=0.27,<1' 'playwright==1.63.0'
WORKDIR /app
COPY bot-loadgen/main.py /app/main.py
CMD ["python", "main.py"]
