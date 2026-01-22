/**
 * Test bcrypt hash compatibility between Python and Node.js
 *
 * Python hash generated with:
 * python -c "import bcrypt; print(bcrypt.hashpw(b'testpassword123', bcrypt.gensalt()).decode())"
 */

// Test both bcryptjs (pure JS) and bcrypt (native C++)
const bcryptjs = require('bcryptjs');
let bcrypt;
try {
  bcrypt = require('bcrypt');
  console.log('✅ Using native bcrypt (C++ bindings)');
} catch (e) {
  bcrypt = bcryptjs;
  console.log('⚠️  Using bcryptjs (pure JavaScript fallback)');
}

// Hash generated from Python bcrypt.hashpw(b'testpassword123', bcrypt.gensalt())
const pythonHash = '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5GyYb9K0rJ5n6';
const testPassword = 'testpassword123';

console.log('🔐 Testing bcrypt compatibility between Python and Node.js\n');
console.log('Password:', testPassword);
console.log('Python-generated hash:', pythonHash);
console.log('\nVerifying with Node.js bcryptjs...\n');

// Test 1: Verify Python hash with Node.js
bcrypt.compare(testPassword, pythonHash)
  .then(result => {
    if (result) {
      console.log('✅ SUCCESS: Node.js bcryptjs can verify Python bcrypt hash');
      console.log('   This means password hashing is compatible!\n');
    } else {
      console.log('❌ FAILURE: Node.js bcryptjs cannot verify Python bcrypt hash');
      console.log('   This is likely the root cause of login timeouts!\n');
    }

    // Test 2: Generate Node.js hash for comparison
    console.log('Generating Node.js bcryptjs hash for comparison...');
    return bcrypt.hash(testPassword, 12);
  })
  .then(nodejsHash => {
    console.log('Node.js-generated hash:', nodejsHash);
    console.log('\nComparing hash formats:');
    console.log('  Python:  ', pythonHash);
    console.log('  Node.js: ', nodejsHash);
    console.log('\nBoth should start with $2b$12$ (bcrypt algorithm, cost factor 12)');

    // Test 3: Verify Node.js hash works
    return bcrypt.compare(testPassword, nodejsHash);
  })
  .then(result => {
    if (result) {
      console.log('✅ Node.js hash verifies correctly (as expected)\n');
    } else {
      console.log('❌ Node.js hash verification failed (unexpected!)\n');
    }
  })
  .catch(err => {
    console.error('❌ Error during bcrypt test:', err);
  });
