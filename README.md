---
title: accompy
emoji: 🎹
colorFrom: blue
colorTo: indigo
sdk: docker
pinned: false
---

# Accompy

A real-time accompanist (for now for piano ideally lol). Select right/left hand, then accompy tracks your tempo and accompanies automatically.

![Accompy demo](docs/images/demo.png)

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Web UI

```bash
python run.py
```

Open [http://localhost:8000](http://localhost:8000) to browse scores, add new pieces, and play.

### Inspiration

A small project of mine that I always wanted to do. Had the idea two years ago but never got the motivation to implement it.
