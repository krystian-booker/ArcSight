import { spawn } from 'child_process';
import { existsSync } from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const repoRoot = path.resolve(__dirname, '..');
const distIndex = path.join(repoRoot, 'app', 'static', 'dist', 'index.html');

const npmCommand = process.platform === 'win32' ? 'npm.cmd' : 'npm';
const pythonCommand =
  process.env.PLAYWRIGHT_PYTHON_COMMAND ??
  (process.env.CONDA_PREFIX || process.env.CONDA_DEFAULT_ENV
    ? 'conda run -n ArcSight --no-capture-output python run.py'
    : 'python run.py');

async function runCommand(command, args, options = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      stdio: 'inherit',
      shell: options.shell ?? false,
      cwd: options.cwd ?? repoRoot,
      env: options.env ?? process.env,
    });

    child.on('error', reject);
    child.on('close', (code) => {
      if (code === 0) {
        resolve(undefined);
      } else {
        reject(new Error(`Command \"${command} ${args.join(' ')}\" exited with code ${code}`));
      }
    });
  });
}

async function ensureFrontendBuild() {
  if (existsSync(distIndex)) {
    return;
  }

  console.log('No frontend build found at %s. Running \"npm run build\" before starting tests...', distIndex);
  await runCommand(npmCommand, ['run', 'build']);
  console.log('✓ Frontend build completed.');
}

async function startBackend() {
  await ensureFrontendBuild();

  const backendProcess = spawn(pythonCommand, {
    stdio: 'inherit',
    shell: true,
    cwd: repoRoot,
    env: process.env,
  });

  const forwardSignal = (signal) => {
    if (backendProcess.killed) {
      return;
    }
    backendProcess.kill(signal);
  };

  process.on('SIGINT', forwardSignal);
  process.on('SIGTERM', forwardSignal);

  backendProcess.on('error', (error) => {
    console.error('Failed to start backend process:', error);
    process.exit(1);
  });

  backendProcess.on('exit', (code, signal) => {
    if (signal) {
      process.kill(process.pid, signal);
    } else {
      process.exit(code ?? 0);
    }
  });
}

startBackend().catch((error) => {
  console.error(error.message || error);
  process.exit(1);
});
