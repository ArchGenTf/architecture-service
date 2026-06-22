FROM python:3.12-slim AS builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

FROM python:3.12-slim
WORKDIR /app
RUN groupadd -r appgroup && useradd -m -r -g appgroup appuser
COPY --chown=appuser:appgroup --from=builder /root/.local /home/appuser/.local
RUN pip install --no-cache-dir --upgrade "wheel>=0.46.2" "jaraco.context>=6.1.0" \
    && HOME=/home/appuser pip install --no-cache-dir --upgrade --user "wheel>=0.46.2" "jaraco.context>=6.1.0"
COPY . .
RUN chown -R appuser:appgroup /app
USER appuser
ENV PATH=/home/appuser/.local/bin:$PATH
EXPOSE 8003
CMD ["python", "main.py"]
