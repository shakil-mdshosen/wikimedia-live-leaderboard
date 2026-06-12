# Wikimedia Live Leaderboard

A live, production-ready tracking leaderboard for Wikimedia Commons edit-a-thons, optimized for deployment on Wikimedia Toolforge.

## Features
- **Live Updates:** Uses Wikimedia EventStreams API (Server-Sent Events) for real-time tracking.
- **Dynamic Editor Registration:** Add editors dynamically; the system uses the MediaWiki Action API to automatically backfill historical edits during the event window.
- **Premium UI:** Vanilla JS/CSS dashboard featuring glassmorphism and real-time polling.
- **Toolforge Ready:** Pre-configured with `Procfile` and `jobs.yaml` for Kubernetes deployment.

## Local Development

1. **Install Dependencies:**
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Run the Backend/API (Terminal 1):**
   ```bash
   uvicorn backend.main:app --reload
   ```

3. **Run the Stream Listener (Terminal 2):**
   ```bash
   python -m worker.stream_listener
   ```

4. **View Dashboard:**
   Open `http://localhost:8000` in your browser.

## Toolforge Deployment

### 1. Web Service
```bash
toolforge webservice buildpack start
```

### 2. Continuous Worker Job
```bash
toolforge jobs load jobs.yaml
```
*(Or manually via: `toolforge jobs run stream-listener --command "python3 worker/stream_listener.py" --image python3.11 --continuous`)*

## Live Demo
Planned URL: [https://live.toolforge.org](https://live.toolforge.org)
