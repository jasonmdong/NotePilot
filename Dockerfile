FROM ubuntu:24.04

ARG AUDIVERIS_VERSION=5.10.2
ARG AUDIVERIS_DEB=Audiveris-${AUDIVERIS_VERSION}-ubuntu24.04-x86_64.deb

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PATH="/home/user/.local/bin:$PATH" \
    AUDIVERIS_BIN="xvfb-run -a /opt/audiveris/bin/Audiveris"

RUN apt-get update && apt-get install -y \
    ca-certificates \
    fontconfig \
    python3 \
    python3-pip \
    python3-venv \
    wget \
    xvfb \
    && rm -rf /var/lib/apt/lists/*

RUN wget -O /tmp/audiveris.deb \
    https://github.com/Audiveris/audiveris/releases/download/${AUDIVERIS_VERSION}/${AUDIVERIS_DEB} \
    && apt-get update \
    && apt-get install -y /tmp/audiveris.deb \
    && rm -f /tmp/audiveris.deb \
    && rm -rf /var/lib/apt/lists/*

RUN xvfb-run -a /opt/audiveris/bin/Audiveris -help >/dev/null

RUN useradd -m -u 1000 user

WORKDIR /app

COPY requirements.space.txt /app/requirements.space.txt
RUN python3 -m pip install --break-system-packages --upgrade pip \
    && python3 -m pip install --break-system-packages -r /app/requirements.space.txt

COPY app.py /app/app.py
COPY src /app/src
COPY static /app/static
COPY LICENSE /app/LICENSE
COPY README.md /app/README.md
COPY supabase_simple_auth.sql /app/supabase_simple_auth.sql

RUN chown -R user:user /app
USER user

CMD ["python3", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860"]
