FROM python:3.12-slim AS builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

FROM python:3.12-slim
WORKDIR /app
RUN groupadd -r appgroup && useradd -m -r -g appgroup appuser
COPY --chown=appuser:appgroup --from=builder /root/.local /home/appuser/.local
# Fix CVE-2026-23949 (jaraco.context<6.1.0) and CVE-2026-24049 (wheel<0.46.2):
# Upgrade system-level packages, then scan the ENTIRE filesystem to purge any remaining
# old-version dist-info directories (covers /usr/local, /usr/lib, user-local, and anywhere else)
RUN pip install --no-cache-dir --upgrade pip "wheel>=0.46.2" "jaraco.context>=6.1.0" \
    && find / -xdev -type d \( \
        -name "wheel-0.4[0-5]*.dist-info" \
        -o -name "jaraco.context-5*.dist-info" \
        -o -name "jaraco_context-5*.dist-info" \
    \) -exec rm -rf {} + 2>/dev/null || true
COPY . .
RUN chown -R appuser:appgroup /app
USER appuser
ENV PATH=/home/appuser/.local/bin:$PATH
EXPOSE 8003
CMD ["python", "main.py"]
