FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PATH="/home/user/.local/bin:$PATH"

RUN useradd -m -u 1000 user

WORKDIR /app

COPY requirements.space.txt /app/requirements.space.txt
RUN pip install --upgrade pip && pip install -r /app/requirements.space.txt

COPY app.py /app/app.py
COPY src /app/src
COPY static /app/static
COPY LICENSE /app/LICENSE
COPY README.md /app/README.md
COPY supabase_simple_auth.sql /app/supabase_simple_auth.sql

RUN chown -R user:user /app
USER user

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860"]

