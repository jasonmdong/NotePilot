---
title: NotePilot
emoji: 🎹
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

# NotePilot

A real-time accompanist and piano practice app. Select right/left hand, then NotePilot tracks your tempo and accompanies automatically. Demo available [here](https://jasonmdong-accompy.hf.space/).

![NotePilot demo](docs/images/demo_v2.png)

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Webapp

```bash
python run.py
```

Open [http://localhost:8000](http://localhost:8000) to browse scores, add new pieces, and play.

### Inspiration

A small project of mine that I always wanted to do. Had the idea two years ago but never got the motivation to implement it.
