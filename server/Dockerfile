# 렌더 무료 서버용. 녹음 길이·음량 처리에 ffmpeg가 필요하다.
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg tzdata && rm -rf /var/lib/apt/lists/* && pip install --no-cache-dir pywebpush==2.5.0
ENV TZ=Asia/Seoul PYTHONUNBUFFERED=1
WORKDIR /app
COPY server.py moderate.py store.py push.py avatar.py ./
COPY web ./web
CMD ["python", "server.py"]
