FROM python:3.12-slim
WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir -r requirements.txt

# prevent token leakage: expect TELEGRAM_TOKEN in env or .env
ENV PYTHONUNBUFFERED=1
CMD ["/bin/bash","-lc","python3 bot.py & uvicorn webapp.server:app --host 0.0.0.0 --port 8080"]
