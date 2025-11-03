/**
 * Utility to wait for Flask server to be ready
 */

export async function waitForServer(
  url: string,
  timeoutMs: number = 30000,
  intervalMs: number = 500
): Promise<void> {
  const startTime = Date.now();

  while (Date.now() - startTime < timeoutMs) {
    try {
      const response = await fetch(url);
      if (response.ok) {
        console.log(`Server is ready at ${url}`);
        return;
      }
    } catch (error) {
      // Server not ready yet, continue waiting
    }

    await new Promise(resolve => setTimeout(resolve, intervalMs));
  }

  throw new Error(`Server at ${url} did not become ready within ${timeoutMs}ms`);
}

export async function waitForServerDown(
  url: string,
  timeoutMs: number = 10000,
  intervalMs: number = 500
): Promise<void> {
  const startTime = Date.now();

  while (Date.now() - startTime < timeoutMs) {
    try {
      await fetch(url);
      // Server still responding, wait more
    } catch (error) {
      // Server is down
      console.log(`Server at ${url} is down`);
      return;
    }

    await new Promise(resolve => setTimeout(resolve, intervalMs));
  }

  throw new Error(`Server at ${url} did not shut down within ${timeoutMs}ms`);
}
