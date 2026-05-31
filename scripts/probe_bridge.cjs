/** Probe the browser bridge on port 9334 */
const WebSocket = require('ws');

async function probe() {
  // Try different WebSocket URLs
  const urls = [
    'ws://127.0.0.1:9334/',
    'ws://127.0.0.1:9334/json/version',
    'ws://127.0.0.1:9334/json/list',
  ];

  for (const url of urls) {
    console.log(`\n--- Probing ${url} ---`);
    try {
      const ws = new WebSocket(url);

      await new Promise((resolve, reject) => {
        const timeout = setTimeout(() => {
          console.log('  Timeout waiting for response');
          ws.close();
          resolve();
        }, 5000);

        ws.on('open', () => {
          console.log('  WebSocket OPEN');

          // Send CDP command
          const msg = JSON.stringify({ id: 1, method: 'Browser.getVersion' });
          console.log('  Sending:', msg);
          ws.send(msg);
        });

        ws.on('message', (data) => {
          const text = data.toString();
          console.log('  MESSAGE:', text.substring(0, 500));
          clearTimeout(timeout);
          ws.close();
          resolve();
        });

        ws.on('close', (code, reason) => {
          console.log('  CLOSED:', code, reason.toString());
          clearTimeout(timeout);
          resolve();
        });

        ws.on('error', (err) => {
          console.log('  ERROR:', err.message);
          clearTimeout(timeout);
          resolve();
        });
      });
    } catch (e) {
      console.log('  Exception:', e.message);
    }
  }

  // Also try raw HTTP GET
  console.log('\n--- HTTP GET /json/version ---');
  const http = require('http');
  await new Promise((resolve) => {
    const req = http.get('http://127.0.0.1:9334/json/version', (res) => {
      let data = '';
      res.on('data', c => data += c);
      res.on('end', () => {
        console.log('  Status:', res.statusCode);
        console.log('  Body:', data.substring(0, 500));
        resolve();
      });
    });
    req.on('error', (e) => { console.log('  Error:', e.message); resolve(); });
    setTimeout(resolve, 5000);
  });

  console.log('\n--- HTTP GET /json/list ---');
  await new Promise((resolve) => {
    const req = http.get('http://127.0.0.1:9334/json/list', (res) => {
      let data = '';
      res.on('data', c => data += c);
      res.on('end', () => {
        console.log('  Status:', res.statusCode);
        console.log('  Body:', data.substring(0, 500));
        resolve();
      });
    });
    req.on('error', (e) => { console.log('  Error:', e.message); resolve(); });
    setTimeout(resolve, 5000);
  });
}

probe().then(() => process.exit(0));
