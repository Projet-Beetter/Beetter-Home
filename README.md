# Beetter Home

Local web application for beehive monitoring, running on a Raspberry Pi. It collects sensor data from the LoRa receiver, stores it in InfluxDB, and exposes a dashboard accessible from the local network.

## Features

- Real-time dashboard with temperature, humidity, sound frequency/amplitude, and light readings per hive
- Alert system with configurable warning and critical thresholds
- Beehive management (add, edit, remove hives)
- Calendar for beekeeper activity notes
- Data export (CSV)
- User account management and role-based access
- i18n support (French and English)
- JWT-based authentication, synchronized with Beetter-Server

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3 · Flask 3.0 |
| Database | PostgreSQL (user/config data) · InfluxDB (time-series sensor data) |
| Auth | JWT (PyJWT) · Flask-Login · Flask-Bcrypt |
| Scheduling | APScheduler |
| Frontend | Jinja2 templates · HTML/CSS/JS |
| Deployment | Docker · Gunicorn · Gevent |

## LoRa Receiver

The `lora/` directory contains the Raspberry Pi-side LoRa scripts:

- `receiver.py` — listens on the LoRa module and forwards packets to the local Flask API (`POST /api/data`)
- `grove_lora.py` — low-level driver for the Grove LoRa module

## Getting Started

```bash
# Copy and fill in your environment variables
cp app/.env.example app/.env

# Start all services with Docker Compose
docker compose -f app/compose.yml up -d
```

See [Beetter-Technical-Documentation](https://github.com/Projet-Beetter/Beetter-Technical-Documentation) for the full deployment guide.

## Project Structure

```
app/
  blueprints/       # Flask blueprints (account, admin, alerts, api, auth,
  │                 #   beehives, calendar, dashboard, export, settings, setup)
  models.py         # SQLAlchemy models
  scheduler.py      # APScheduler jobs
  i18n.py           # Internationalisation helpers
  Dockerfile
  compose.yml
lora/
  receiver.py       # LoRa → Flask API bridge
  grove_lora.py     # Grove LoRa module driver
```

## License

[CC BY-NC 4.0](LICENSE) — Projet Beetter, ESIEE Paris
