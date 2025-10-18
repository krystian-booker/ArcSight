# vision-tools

A Flask-based web application for vision processing and camera management. Supports multiple camera types (USB, GenICam, OAK-D) with real-time video streaming and configurable vision pipelines (AprilTag detection, colored shape detection, ML object detection).

## Quick Start

### Installation

1. **Create and activate the Conda environment:**
   ```bash
   conda env create -f environment.yml
   conda activate vision-tools
   ```

2. **Run the web server (production mode):**
   ```bash
   python run.py
   ```

   The web server will be available at `http://0.0.0.0:8080`.

## Development Setup

### Prerequisites

- Conda (miniconda or anaconda)
- Python 3.11
- Camera hardware (optional for development)

### Setting Up Development Environment

1. **Create and activate the Conda environment:**
   ```bash
   conda env create -f environment.yml
   conda activate vision-tools
   ```

2. **Configure environment variables (optional):**

   Copy the example environment file:
   ```bash
   cp .env.example .env
   ```

   Edit `.env` to customize your configuration. For development, set:
   ```bash
   FLASK_ENV=development
   # or
   FLASK_DEBUG=1
   ```

3. **Run in development mode:**

   **Option 1: Using environment variable**
   ```bash
   # Linux/macOS
   FLASK_ENV=development python run.py

   # Windows (PowerShell)
   $env:FLASK_ENV="development"; python run.py

   # Windows (Command Prompt)
   set FLASK_ENV=development && python run.py
   ```

   **Option 2: Using .env file**

   Edit `.env` and set `FLASK_ENV=development`, then:
   ```bash
   python run.py
   ```

### Running for Production/Competition

**IMPORTANT:** Always run in production mode on competition robots!

```bash
# Production mode (default - debug disabled)
python run.py

# Or explicitly set environment
FLASK_ENV=production python run.py
```

Production mode ensures:
- ✅ Debug mode disabled (no security risks)
- ✅ No auto-reload (no wasted CPU)
- ✅ Optimized performance
- ✅ Minimal error exposure

### Environment Variables

| Variable | Description | Default | Values |
|----------|-------------|---------|--------|
| `FLASK_ENV` | Application environment | `production` | `development`, `production`, `testing` |
| `FLASK_DEBUG` | Enable debug mode | `0` | `0` (off), `1` (on) |
| `HOST` | Server host address | `0.0.0.0` | Any valid IP address |
| `PORT` | Server port | `8080` | Any valid port number |
| `SECRET_KEY` | Secret key for sessions/CSRF | Auto-generated | Any random string (32+ chars) |
| `DATABASE_URL` | Database connection string | SQLite in user data dir | Any valid SQLAlchemy URL |

See `.env.example` for more details.

## Web Interface

The web interface provides:
- **Dashboard**: View live camera feeds and pipeline outputs
- **Camera Management**: Configure cameras (USB, GenICam, OAK-D)
- **Pipeline Configuration**: Set up vision pipelines (AprilTag, colored shapes, ML detection)
- **Calibration Tools**: Camera calibration utilities
- **Settings**: Application-wide settings

## Architecture

- **Camera Drivers**: Modular driver system (USB, GenICam, OAK-D)
- **Threading Model**: Separate acquisition and processing threads per camera
- **Frame Buffer Pooling**: Efficient memory management with automatic shrinking
- **Lazy JPEG Encoding**: Frames encoded only when clients request them
- **SQLite Database**: Configuration stored in user data directory
