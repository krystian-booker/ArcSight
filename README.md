# vision-tools

A Flask-based web application for vision processing and camera management. Supports multiple camera types (USB, GenICam, OAK-D) with real-time video streaming and configurable vision pipelines (AprilTag detection, colored shape detection, ML object detection).

## Quick Start

### Installation

1. **Install dependencies using Pixi:**
   ```bash
   pixi install
   ```

2. **Run the web server (development mode):**
   ```bash
   pixi run dev
   ```

   The web server will be available at `http://0.0.0.0:8080`.

3. **Run the web server (production mode):**
   ```bash
   pixi run serve
   ```

## Development Setup

### Prerequisites

- [Pixi](https://pixi.sh) - Modern package manager for Python projects ([installation instructions](https://pixi.sh/latest/#installation))
- Camera hardware (optional for development)

Pixi will automatically install Python 3.11 and all dependencies.

### Setting Up Development Environment

1. **Install project dependencies:**
   ```bash
   pixi install
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
   ```bash
   pixi run dev
   ```

### Common Development Tasks

```bash
# Run development server
pixi run dev

# Run tests
pixi run test

# Run tests with verbose output
pixi run test-verbose

# Run tests without coverage
pixi run test-no-cov

# Run specific test file
pixi run test tests/test_camera_manager.py

# Format code
pixi run format

# Check code quality
pixi run lint
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
