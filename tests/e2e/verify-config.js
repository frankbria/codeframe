#!/usr/bin/env node
/**
 * Verification script for Playwright configuration.
 * Checks that webServer array is correctly configured.
 */

const { execSync } = require('child_process');

console.log('🔍 Verifying Playwright configuration...\n');

try {
  // 1. Check TypeScript compilation
  console.log('1. Checking TypeScript compilation...');
  execSync('npx tsc --noEmit playwright.config.ts', { stdio: 'inherit' });
  console.log('   ✅ TypeScript compilation passed\n');

  // 2. Import and validate config
  console.log('2. Validating configuration structure...');
  const config = require('./playwright.config.ts').default;

  // Check webServer configuration
  const { webServer } = config;

  if (process.env.CI) {
    if (webServer === undefined) {
      console.log('   ✅ CI mode: webServer is undefined (correct)\n');
    } else {
      console.error('   ❌ CI mode: webServer should be undefined');
      process.exit(1);
    }
  } else {
    if (Array.isArray(webServer)) {
      console.log(`   ✅ Development mode: webServer is an array with ${webServer.length} servers`);

      webServer.forEach((server, idx) => {
        console.log(`      Server ${idx + 1}:`);
        console.log(`         URL: ${server.url}`);
        console.log(`         Command: ${server.command.substring(0, 60)}...`);
      });

      // Verify backend server is first
      if (webServer[0].url.includes('8080/health')) {
        console.log('   ✅ Backend server (port 8080) is configured');
      } else {
        console.error('   ❌ Backend server should be on port 8080');
        process.exit(1);
      }

      // Verify frontend server is second
      if (webServer[1].url.includes('3000')) {
        console.log('   ✅ Frontend server (port 3000) is configured');
      } else {
        console.error('   ❌ Frontend server should be on port 3000');
        process.exit(1);
      }

      console.log('');
    } else {
      console.error('   ❌ webServer should be an array in development mode');
      process.exit(1);
    }
  }

  // 3. Check backend server command
  console.log('3. Verifying backend server command...');
  const backendServer = !process.env.CI && Array.isArray(webServer) ? webServer[0] : null;

  if (backendServer) {
    const { command } = backendServer;

    if (command.includes('uv run uvicorn')) {
      console.log('   ✅ Uses uv package manager (correct)');
    } else {
      console.error('   ❌ Should use "uv run uvicorn"');
      process.exit(1);
    }

    if (command.includes('codeframe.ui.server:app')) {
      console.log('   ✅ Correct FastAPI app path');
    } else {
      console.error('   ❌ Should reference "codeframe.ui.server:app"');
      process.exit(1);
    }

    if (command.includes('--port 8080')) {
      console.log('   ✅ Correct port (8080)');
    } else {
      console.error('   ❌ Should use port 8080');
      process.exit(1);
    }

    console.log('');
  }

  console.log('✅ All configuration checks passed!\n');
  console.log('Next steps:');
  console.log('  1. Run: cd tests/e2e && npx playwright test');
  console.log('  2. Playwright will auto-start both backend and frontend servers');
  console.log('  3. Backend health check: http://localhost:8080/health');
  console.log('  4. Frontend URL: http://localhost:3000\n');

} catch (error) {
  console.error('❌ Configuration verification failed:', error.message);
  process.exit(1);
}
