import { ChildProcess } from 'child_process';
import { waitForServerDown } from './utils/wait-for-server';

/**
 * Global teardown runs once after all tests
 * Stops Flask server gracefully
 */
async function globalTeardown() {
  console.log('Shutting down Flask server...');

  const flaskProcess: ChildProcess = (global as any).__FLASK_PROCESS__;

  if (flaskProcess) {
    // Send SIGTERM for graceful shutdown
    flaskProcess.kill('SIGTERM');

    // Wait for process to exit
    await new Promise<void>((resolve) => {
      flaskProcess.on('exit', () => {
        console.log('Flask server stopped');
        resolve();
      });

      // Force kill after 5 seconds if not stopped
      setTimeout(() => {
        if (!flaskProcess.killed) {
          console.log('Force killing Flask server...');
          flaskProcess.kill('SIGKILL');
          resolve();
        }
      }, 5000);
    });

    try {
      await waitForServerDown('http://localhost:8080', 5000);
    } catch (error) {
      console.warn('Could not verify server shutdown:', error);
    }
  }

  console.log('Teardown complete');
}

export default globalTeardown;
