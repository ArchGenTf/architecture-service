FROM python:3.12-slim AS builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

FROM python:3.12-slim
WORKDIR /app
RUN groupadd -r appgroup && useradd -m -r -g appgroup appuser
COPY --chown=appuser:appgroup --from=builder /root/.local /home/appuser/.local
COPY . .
RUN chown -R appuser:appgroup /app
USER appuser
ENV PATH=/home/appuser/.local/bin:$PATH
EXPOSE 8003
CMD ["python", "main.py"]
