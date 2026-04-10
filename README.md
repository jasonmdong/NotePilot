# Accompy

A real-time piano accompanist. You play the right-hand melody — accompy tracks your tempo and plays the left hand automatically.

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

## Desktop App (v1)

The first desktop version wraps the existing FastAPI app in Electron and starts a local Python backend automatically.

### Quick start for a new macOS tester

```bash
git clone https://github.com/jasonmdong/accompy
cd accompy
./scripts/setup_desktop_mac.sh
./scripts/run_desktop_mac.sh
```

What a new user needs installed first:

- `Python 3.11` or newer
- `npm` / Node.js
- `Audiveris` if they want PDF/image import

What happens after launch:

- The desktop app opens like a normal app window.
- Score files are stored in the user's local app data folder, not in the repo:
  - `~/Library/Application Support/accompy/scores`
- On first launch, starter scores from the repo are copied there once.
- New imports/conversions also go there.

### Quick start for a new Windows tester

In PowerShell:

```powershell
git clone <your-repo-url>
cd accompy
powershell -ExecutionPolicy Bypass -File .\scripts\setup_desktop_windows.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\run_desktop_windows.ps1
```

What a new Windows user needs installed first:

- `Python 3`
- `npm` / Node.js
- `Audiveris` if they want PDF/image import

Where score files live on Windows:

- `%APPDATA%\accompy\scores`

On first launch, starter scores from the repo are copied there once.

### Manual setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
npm install
npm run desktop
```

Notes:

- The Electron app looks for Python in `.venv/bin/python3` first.
- If your Python lives elsewhere, start with `PYTHON_PATH=/path/to/python npm run desktop`.
- The desktop shell starts the backend on `127.0.0.1:8765`.
- In desktop mode, user score files are stored outside the repo in the app data folder:
  - macOS: `~/Library/Application Support/accompy/scores`
  - Windows: `%APPDATA%\accompy\scores`
- On first launch, the bundled repo `scores/` files are copied there as starter content. After that, the desktop app reads and writes from the user-local folder.
- To create a first packaged mac build directory:

```bash
npm run desktop:dist
```

- To attempt a macOS DMG build:

```bash
npm run desktop:dmg
```

- To create a first packaged Windows directory build:

```powershell
npm run desktop:dist:win
```

- To create a first Windows installer build:

```powershell
npm run desktop:nsis
```

This is still a thin desktop wrapper around the current web app, not yet a fully standalone app with bundled Python/Audiveris. A tester still needs local dependencies installed.

## Self-contained macOS beta build

If you want to test a more app-like mac build that bundles the Python backend:

```bash
./scripts/setup_desktop_mac.sh
pip install pyinstaller
./scripts/build_backend_mac.sh
npm run desktop:dmg
```

What this bundles:

- Electron shell
- Python backend binary
- static frontend files
- starter scores copied into the app bundle

What this still does not bundle:

- `Audiveris`

So the packaged beta can run without a separate Python install, but PDF/image import still needs Audiveris on the tester's Mac.

For Windows, the equivalent bundled-backend flow is:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_desktop_windows.ps1
.venv\Scripts\python.exe -m pip install pyinstaller
powershell -ExecutionPolicy Bypass -File .\scripts\build_backend_windows.ps1
npm run desktop:nsis
```

That gives you a Windows installer build with the Python backend bundled, but Audiveris still remains an external dependency if the user wants PDF/image import.

## CLI

```bash
# Computer keyboard
python -m src.main --keyboard --score twinkle

# USB MIDI keyboard (e.g. Yamaha P-71)
python -m src.main --score mozart_k545

# List available scores
python -m src.main --list
```

You'll be prompted for a starting BPM. The left hand plays between your notes and waits at each melody note until you play it.

### Keyboard layout

```
A = C   S = D   D = E   J = F   K = G   L = A   ; = B
Hold Shift for sharps. The app automatically chooses the octave for the current note.
```

## Adding pieces

Via the web UI — click **+ Add piece** and search the built-in library (535 pieces).

Or via CLI:

```bash
# Built-in corpus
python -m src.convert_score corpus:mozart/k545/movement1_exposition --name mozart_k545

# Downloaded MusicXML
python -m src.convert_score ~/Downloads/mysong.mxl --name mysong

# Show notes + keyboard keys for a score
python -m src.convert_score --show mozart_k545
```

Free MusicXML sources: [IMSLP](https://imslp.org) · [Flat.io](https://flat.io)

## Supabase Migration (in progress)

To start moving score storage out of the local `scores/` folder and into Supabase:

1. Copy `.env.example` to `.env`
2. Fill in:
   - `SUPABASE_URL`
   - `SUPABASE_ANON_KEY`
   - `SUPABASE_SERVICE_ROLE_KEY`
3. Run [`supabase_simple_auth.sql`](supabase_simple_auth.sql) in the Supabase SQL editor.

With those values present, the backend will:

- list scores from Supabase
- load scores from Supabase
- save converted/imported scores into Supabase
- store app-level users and sessions using simple username/password auth

The local filesystem remains as a fallback when Supabase is not configured.
