# Vision Tools Frontend

This directory contains the React + TypeScript single-page application that powers the Vision Tools UI. The project is built with [Vite](https://vitejs.dev/) and styled using Tailwind CSS.

## Getting started

```bash
cd web/frontend
npm install
```

### Local development

Start the Vite development server with hot module replacement:

```bash
npm run dev
```

By default the dev server runs on [http://localhost:5173](http://localhost:5173). The Flask backend exposes REST APIs on port 8080; you can configure Vite's proxy in `vite.config.ts` if you need to forward API requests during development.

### Production build

Build optimized static assets that can be served by the Flask application:

```bash
npm run build
```

The compiled files are written to `web/frontend/dist/`. Run this command before starting the Flask server to ensure the UI is available.

### Linting

```bash
npm run lint
```

This runs the ESLint rules configured for the project to keep the codebase consistent.
