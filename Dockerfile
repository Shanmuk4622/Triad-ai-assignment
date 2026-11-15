FROM mongo:8.0-noble

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3-venv tesseract-ocr tesseract-ocr-eng tini \
    && rm -rf /var/lib/apt/lists/* \
    && python3 -m venv /opt/venv \
    && mkdir -p /app /home/dms/data \
    && chown -R 1000:1000 /home/dms

ENV PATH="/opt/venv/bin:$PATH" HOME=/home/dms PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 OMP_THREAD_LIMIT=1
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY dms/ ./dms/
COPY tests/ ./tests/
COPY start.py ./

USER 1000:1000
EXPOSE 7860
ENTRYPOINT ["tini", "-g", "--"]
CMD ["python", "start.py"]
