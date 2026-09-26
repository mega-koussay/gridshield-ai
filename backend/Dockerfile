FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend ./backend
COPY scripts ./scripts
RUN mkdir -p backend/models backend/data backend/reports

WORKDIR /app/backend
EXPOSE 8000

# Models train automatically on first boot if artifacts are absent.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
