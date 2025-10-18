# vision-tools

A Flask-based web application for vision processing and camera management. Supports multiple camera types (USB, GenICam, OAK-D) with real-time video streaming and configurable vision pipelines (AprilTag detection, colored shape detection, ML object detection).

## Quick Start

### Installation

1. **Create and activate conda environment:**
   ```bash
   conda env create -f environment.yml
   conda activate vision-tools
   ```

2. **Run the web server (development mode):**
   ```bash
   python run.py
   ```

   The web server will be available at `http://0.0.0.0:8080`.

## Development Setup

### Prerequisites

- [Conda](https://docs.conda.io/en/latest/) or [Miniconda](https://docs.conda.io/en/latest/miniconda.html)
- Camera hardware (optional for development)

Conda will automatically install Python 3.11 and all dependencies.

### Setting Up Development Environment

1. **Create the conda environment:**
   ```bash
   conda env create -f environment.yml
   ```

2. **Activate the environment:**
   ```bash
   conda activate vision-tools
   ```

3. **Configure environment variables (optional):**

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

4. **Run in development mode:**
   ```bash
   python run.py
   ```

### Common Development Tasks

```bash
# Activate environment (always do this first)
conda activate vision-tools

# Run development server
python run.py

# Run tests
pytest

# Run tests with verbose output
pytest -v

# Run tests without coverage
pytest --no-cov

# Run specific test file
pytest tests/test_camera_manager.py

# Format code
ruff format app tests

# Check code quality
ruff check app tests
```

### Environment Variables

| Variable | Description | Default | Values |
|----------|-------------|---------|--------|
| `FLASK_ENV` | Application environment | `production` | `development`, `production`, `testing` |
| `FLASK_DEBUG` | Enable debug mode | `0` | `0` (off), `1` (on) |
| `HOST` | Server host address | `0.0.0.0` | Any valid IP address |
| `PORT` | Server port | `8080` | Any valid port number |
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
