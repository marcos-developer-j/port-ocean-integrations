FROM python:3.12-slim
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir "port-ocean[cli]>=0.18.0"
CMD ["ocean", "sail"]
