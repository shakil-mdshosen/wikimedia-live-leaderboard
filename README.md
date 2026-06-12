# Wikimedia Live Leaderboard

A real-time, multi-tenant leaderboard application designed to track contributions during Wikimedia edit-a-thons and events. 

This tool is built to run on **Wikimedia Cloud Services (Toolforge)**. It allows administrators to create tracking events, set time boundaries, add editors, and display a live updating leaderboard tracking **Total Edits**, **File Uploads**, and **Bytes Added** across target wikis.

---

## 🌟 Features

* **Multi-Tenant Architecture**: Host multiple distinct events (e.g., `/event/dhaka-editathon`, `/event/wiki-loves-earth`) simultaneously from a single deployment.
* **Wikimedia OAuth 2.0 Integration**: Secure login using Wikimedia accounts. Only the event creator or the superadmin can manage an event.
* **Live Stats Polling**: A continuous backend worker queries Wikimedia APIs every 5 minutes. The frontend pulls these stats every 30 seconds to provide a "live" feel.
* **Graceful Conclusion**: When an event's end time is reached, the UI automatically transitions to an "Event has ended" state, and the background poller stops querying the API for that event, safely preserving the final tallies in the database.
* **Modern UI**: A responsive, glassmorphism-inspired design with real-time UI updates.

---

## 🏗️ Architecture Stack

* **Backend**: Python 3.11 + FastAPI + Uvicorn
* **Database**: SQLite + SQLAlchemy (ORM)
* **Frontend**: Vanilla HTML / CSS / JavaScript (No build step required for frontend assets)
* **Background Worker**: Custom Python continuous loop script (`worker/poller.py`)
* **Deployment**: Toolforge Buildservice (Cloud Native Buildpacks)

### Directory Structure

```text
wikimedia-live-leaderboard/
├── backend/
│   ├── main.py        # FastAPI application, route handlers, and REST API
│   ├── auth.py        # OAuth 2.0 authentication flow with Wikimedia
│   ├── database.py    # SQLAlchemy setup and session management
│   └── models.py      # Database schema (User, Event, EventEditor)
├── frontend/          # Static HTML/CSS/JS files
│   ├── home.html      # Landing page displaying all active events
│   ├── dashboard.html # User hub for managing their own events
│   ├── event.html     # The public, read-only live leaderboard
│   ├── edit.html      # Admin-only page for editing event settings/editors
│   └── style.css      # Global stylesheet
├── worker/
│   └── poller.py      # Continuous script that queries Wikimedia APIs
├── .env.template      # Template for environment variables
├── requirements.txt   # Python dependencies
└── jobs.yaml          # Toolforge continuous jobs configuration
```

---

## 🚀 Deployment Guide (Wikimedia Toolforge)

These instructions assume you are deploying to a Toolforge tool account (e.g., `tools.live`).

### 1. Initial Setup

SSH into the Toolforge bastion and switch to your tool account:
```bash
become <your-tool-name>
mkdir -p ~/src
cd ~/src
git clone https://github.com/shakil-mdshosen/wikimedia-live-leaderboard.git .
```

### 2. Configure Environment Variables

Create a `.env` file in the root of the project (`~/src/.env`) and define your OAuth credentials:
```ini
WIKIMEDIA_CLIENT_ID="your_oauth_client_id_here"
WIKIMEDIA_CLIENT_SECRET="your_oauth_client_secret_here"
OAUTH_CALLBACK_URL="https://<your-tool-name>.toolforge.org/oauth/callback"
```
*(You can generate OAuth 2.0 credentials on Meta-Wiki at Special:OAuthConsumerRegistration).*

### 3. Deploy the Webservice

This project uses the Toolforge Buildservice. To build the container image and start the web server:

```bash
# 1. Start the build process
toolforge build start https://github.com/shakil-mdshosen/wikimedia-live-leaderboard.git

# 2. Wait for the build to finish successfully
toolforge build show

# 3. Start the webservice mapping to the built image
toolforge webservice buildservice restart --mount all
```
*Note: `--mount all` is critical as it mounts the NFS file system so the SQLite database is persisted across container restarts.*

### 4. Start the Background Poller

The background poller (`worker/poller.py`) is responsible for fetching stats from the Wikimedia API. It runs as a continuous Toolforge job.

```bash
# Load the jobs configuration
toolforge jobs load jobs.yaml
```

You can check the logs of the background worker at any time:
```bash
cat ~/stream-listener.err
cat ~/stream-listener.out
```

---

## 🛠️ Modifying the Application

### Changing the Frontend (HTML/CSS/JS)
Frontend files are baked into the container image during the build process. If you modify any file inside `frontend/`, you **must** rebuild the image:
```bash
cd ~/src
git pull
toolforge build start https://github.com/shakil-mdshosen/wikimedia-live-leaderboard.git
# Wait for SUCCESS...
toolforge webservice buildservice restart --mount all
```

### Changing the Background Poller (`worker/poller.py`)
If you modify the logic that calculates edits or file uploads, you only need to flush and restart the continuous job:
```bash
cd ~/src
git pull
toolforge jobs flush
toolforge jobs load jobs.yaml
```

---

## 🛡️ Guidelines & Security

1. **Superadmin Privileges**: By default, the system recognizes the user `MdsShakil` as the superadmin in `backend/auth.py`. The superadmin can edit and delete *any* event. To change the superadmin, update the username logic in `backend/auth.py`.
2. **Database Migrations**: Because this uses SQLite (`app.db`), schema changes require a migration script (like `migrate_v2.py`) or manually deleting the `app.db` file to recreate the tables from scratch.
3. **API Limits**: The background poller is designed to fetch in 5-minute increments using `uclimit=max` to respect Wikimedia API rate limits. Be cautious about lowering the 5-minute sleep interval, as polling too frequently for events with hundreds of users could trigger API blocks.

---

**Created by**: [Shakil Hosen](https://meta.wikimedia.org/wiki/User:MdsShakil)
