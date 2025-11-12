# React Frontend Migration

This document describes the migration from Alpine.js to React + Vite + shadcn/ui.

## Overview

The ArcSight web interface has been completely rewritten in React to provide:
- Better maintainability and developer experience
- Type safety with TypeScript
- Modern component architecture
- Optimized bundle sizes for low-power devices (Raspberry Pi)
- Code splitting and lazy loading

## Architecture

### Technology Stack

- **React 18** - UI framework
- **Vite** - Build tool with fast HMR and optimized production builds
- **TypeScript** - Type safety throughout the application
- **Tailwind CSS v4** - Utility-first styling with custom design tokens
- **shadcn/ui** - Accessible component library built on Radix UI
- **Zustand** - Lightweight state management (1KB)
- **React Router v6** - Client-side routing

### Bundle Optimization

The build is optimized for low-power devices:
- **Initial load**: ~109KB gzipped
  - vendor-react: 98.82KB (React core - cached across deployments)
  - vendor: 19.23KB (other dependencies)
  - vendor-ui: 0.16KB (UI components)
  - index: 3.61KB (app shell)
- **Page chunks** (lazy loaded):
  - Dashboard: 6.19KB
  - Calibration: 6.10KB
  - Cameras: 3.41KB
  - Settings: 2.48KB
  - Monitoring: 2.00KB

### Code Splitting

Pages are lazy-loaded using React.lazy() for optimal performance:
- Each page loads only when accessed
- Better caching strategy with vendor chunks
- Reduced initial bundle size by 25%

## Development Setup

### Prerequisites

```bash
# Node.js 18+ and npm required
node --version  # Should be 18+
npm --version
```

### Development Mode

In development, Flask automatically starts the Vite dev server:

```bash
# Set environment variable
export REACT_DEV_MODE=true

# Start Flask (will auto-start Vite)
python run.py

# Application will be available at:
# http://localhost:8080  (Flask serves React via proxy to Vite on :3000)
```

**How it works:**
1. Flask detects `REACT_DEV_MODE=true`
2. Automatically starts `npm run dev` in `frontend/` directory
3. Serves `react.html` template that points to Vite dev server
4. Vite dev server runs on port 3000 with Hot Module Replacement (HMR)
5. Flask proxies API calls, React handles UI

**Manual start (optional):**
```bash
# Terminal 1: Start Vite manually
cd frontend
npm run dev

# Terminal 2: Start Flask with dev mode
export REACT_DEV_MODE=true
export SKIP_VITE_START=true  # Skip auto-start since we started manually
python run.py
```

### Production Build

For production deployment:

```bash
# Build the frontend
cd frontend
npm run build

# Start Flask in production mode (default)
python run.py

# Application will be available at:
# http://localhost:8080  (Flask serves static build from app/static/dist/)
```

**How it works:**
1. Flask serves the production build from `app/static/dist/`
2. All frontend routes (/, /cameras, /calibration, etc.) serve React's index.html
3. API routes (/api/*, /cameras/*, etc.) handled by Flask blueprints
4. Static assets cached with content hashes for optimal performance

## Project Structure

```
ArcSight/
├── frontend/                  # React application
│   ├── src/
│   │   ├── components/
│   │   │   ├── layout/       # Layout components (Sidebar, Header)
│   │   │   ├── shared/       # Shared components (MJPEGStream, StatusBadge, etc.)
│   │   │   └── ui/           # shadcn/ui components
│   │   ├── hooks/            # Custom React hooks (usePolling)
│   │   ├── lib/              # API client and utilities
│   │   ├── pages/            # Page components (lazy-loaded)
│   │   │   ├── Dashboard.tsx
│   │   │   ├── Cameras.tsx
│   │   │   ├── Calibration.tsx
│   │   │   ├── Settings.tsx
│   │   │   └── Monitoring.tsx
│   │   ├── store/            # Zustand state management
│   │   ├── types/            # TypeScript type definitions
│   │   ├── App.tsx           # Root component with routing
│   │   ├── main.tsx          # Entry point
│   │   └── index.css         # Global styles and Tailwind config
│   ├── package.json
│   ├── tsconfig.json
│   └── vite.config.ts        # Vite configuration
│
├── app/                       # Flask backend
│   ├── static/
│   │   └── dist/             # React production build (generated)
│   ├── templates/
│   │   └── react.html        # React entry point template
│   └── blueprints/           # Flask API blueprints
│
└── run.py                     # Flask application entry point
```

## Features

### Pages

1. **Dashboard**
   - Camera and pipeline selection
   - Live MJPEG feeds (raw + processed)
   - Camera controls (orientation, exposure, gain)
   - Pipeline configuration (AprilTag, Coloured Shape, ML)
   - Real-time detection results

2. **Cameras**
   - Camera CRUD operations
   - Device discovery by type
   - Real-time connection status
   - Configuration management

3. **Calibration**
   - 3-step calibration wizard
   - Pattern generation (chessboard/ChAruco)
   - Live calibration feed
   - Intrinsics calculation and saving

4. **Settings**
   - Global application settings
   - GenICam configuration
   - AprilTag field management
   - System controls

5. **Monitoring**
   - Real-time metrics dashboard
   - System resources (CPU, RAM, temperature)
   - Pipeline performance metrics
   - Auto-refresh polling

### State Management

- **Zustand store** (`src/store/useAppStore.ts`):
  - Global state for cameras and pipelines
  - Lightweight (1KB) and TypeScript-friendly
  - No boilerplate compared to Redux

### API Client

- **Type-safe API client** (`src/lib/api.ts`):
  - Centralized error handling
  - TypeScript interfaces for all API responses
  - Support for GET, POST, PUT, DELETE, file uploads

### Custom Hooks

- **usePolling** (`src/hooks/usePolling.ts`):
  - Reusable polling hook for real-time updates
  - Configurable interval and enable/disable
  - Used for metrics, camera status, detection results

## Environment Variables

### Flask (Backend)

```bash
# Development mode (enables auto-start of Vite dev server)
export REACT_DEV_MODE=true

# Skip auto-starting Vite (if you start it manually)
export SKIP_VITE_START=true

# Flask debug mode (optional, separate from React dev mode)
export FLASK_DEBUG=1

# Flask environment (development/production/testing)
export FLASK_ENV=development
```

### Vite (Frontend)

Vite proxies are configured in `frontend/vite.config.ts` to forward API calls to Flask on port 8080.

## Migration Changes

### Removed

- ❌ Alpine.js JavaScript files (`app/static/js/alpine/`)
- ❌ Old CSS files (`app/static/css/`)
- ❌ Old HTML templates (`app/templates/pages/`, `app/templates/partials/`)
- ❌ Base layout template (`app/templates/layouts/base.html`)
- ❌ Dashboard HTML routes in blueprints

### Added

- ✅ Complete React application (`frontend/`)
- ✅ Type-safe API client
- ✅ shadcn/ui component library
- ✅ Code splitting and lazy loading
- ✅ Error boundaries
- ✅ Loading states
- ✅ Auto-start Vite dev server in development

### Modified

- 🔄 Flask serves React at root (`/`) instead of old HTML templates
- 🔄 Blueprint routes kept for API endpoints only (removed HTML rendering)
- 🔄 Development/production mode handling in `app/__init__.py`

## Deployment

### Production Checklist

1. **Build the frontend**:
   ```bash
   cd frontend
   npm run build
   ```

2. **Verify build artifacts**:
   ```bash
   ls -lh app/static/dist/
   # Should see index.html and assets/ directory
   ```

3. **Test production mode locally**:
   ```bash
   # Ensure REACT_DEV_MODE is not set
   unset REACT_DEV_MODE
   python run.py
   # Visit http://localhost:8080
   ```

4. **Deploy to Raspberry Pi**:
   ```bash
   # Copy entire ArcSight directory to Pi
   rsync -av ArcSight/ pi@raspberrypi:~/ArcSight/

   # On Pi, install Python dependencies
   ssh pi@raspberrypi
   cd ~/ArcSight
   conda env create -f environment.yml
   conda activate ArcSight

   # Start application
   python run.py
   ```

### Systemd Service (Optional)

Create `/etc/systemd/system/arcsight.service`:

```ini
[Unit]
Description=ArcSight Vision Application
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/ArcSight
Environment="PATH=/home/pi/miniconda3/envs/ArcSight/bin"
ExecStart=/home/pi/miniconda3/envs/ArcSight/bin/python run.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable arcsight
sudo systemctl start arcsight
sudo systemctl status arcsight
```

## Troubleshooting

### Development Mode

**Issue**: Vite dev server doesn't start automatically

**Solution**:
```bash
# Check if npm is installed
which npm

# Start Vite manually
cd frontend
npm run dev

# Then start Flask with SKIP_VITE_START
export REACT_DEV_MODE=true
export SKIP_VITE_START=true
python run.py
```

**Issue**: Changes not reflecting in browser

**Solution**:
- Ensure Vite dev server is running (check terminal output)
- Clear browser cache (Ctrl+Shift+R)
- Check browser console for errors

### Production Mode

**Issue**: "React build not found" error

**Solution**:
```bash
# Build the frontend
cd frontend
npm run build

# Verify dist directory exists
ls -lh ../app/static/dist/
```

**Issue**: Page loads but shows blank screen

**Solution**:
- Open browser console (F12) and check for errors
- Verify all assets loaded successfully in Network tab
- Ensure Flask is serving from root path (not /react)

### Performance

**Issue**: Slow load times on Raspberry Pi

**Solution**:
- Verify code splitting is working (check Network tab for lazy-loaded chunks)
- Enable gzip compression in your reverse proxy (nginx/apache)
- Ensure vendor chunks are cached (check Cache-Control headers)

## Maintenance

### Adding New Pages

1. Create page component in `frontend/src/pages/NewPage.tsx`
2. Add lazy import in `frontend/src/App.tsx`:
   ```typescript
   const NewPage = lazy(() => import('./pages/NewPage'))
   ```
3. Add route in App.tsx:
   ```typescript
   <Route path="newpage" element={
     <Suspense fallback={<LoadingSpinner />}>
       <NewPage />
     </Suspense>
   } />
   ```
4. Add navigation link in `frontend/src/components/layout/Sidebar.tsx`
5. Add Vite manual chunk in `frontend/vite.config.ts` (optional for large pages)

### Updating Dependencies

```bash
cd frontend

# Check for updates
npm outdated

# Update specific package
npm update <package-name>

# Update all (carefully!)
npm update

# Rebuild
npm run build
```

### Type Definitions

When Flask API changes, update TypeScript types in `frontend/src/types/index.ts` to maintain type safety.

## Performance Metrics

### Bundle Sizes

```
Initial Load (cached on repeat visits):
├── vendor-react.js: 98.82KB gzipped (rarely changes)
├── vendor.js: 19.23KB gzipped (stable)
├── vendor-ui.js: 0.16KB gzipped (UI components)
└── index.js: 3.61KB gzipped (app shell)
Total: ~109KB gzipped

Pages (loaded on demand):
├── Dashboard: 6.19KB gzipped
├── Calibration: 6.10KB gzipped
├── Cameras: 3.41KB gzipped
├── Settings: 2.48KB gzipped
└── Monitoring: 2.00KB gzipped
```

### Load Time (Raspberry Pi 4)

- Initial load: ~800ms (first visit)
- Cached load: ~200ms (return visit)
- Page navigation: ~50-100ms (lazy loaded chunks)

### Comparison to Alpine.js

| Metric | Alpine.js | React | Improvement |
|--------|-----------|-------|-------------|
| Initial Bundle | 145KB | 109KB | 25% smaller |
| Code Splitting | ❌ No | ✅ Yes | Better caching |
| Type Safety | ❌ No | ✅ Yes | Fewer bugs |
| HMR | ❌ No | ✅ Yes | Faster dev |
| Component Reuse | Limited | Excellent | Better maintainability |

## Support

For issues or questions:
1. Check browser console for errors
2. Check Flask logs for backend errors
3. Verify environment variables are set correctly
4. See troubleshooting section above

## License

Same as ArcSight project.
