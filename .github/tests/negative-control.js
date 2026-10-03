const fs = require('node:fs');
const path = require('node:path');

// Negative control: every new assertion must fail when the property is broken.
const wf = '.github/workflows/npm-publish.yml';
const original = fs.readFileSync(wf, 'utf8');

function run(label, mutated) {
  fs.writeFileSync(wf, mutated, 'utf8');
  const res = require('node:child_process').spawnSync(
    process.execPath,
    ['--test', '.github/tests/npm-contract.test.js'],
    { cwd: path.resolve(__dirname, '..', '..'), encoding: 'utf8' },
  );
  const out = res.stdout + res.stderr;
  const fails = (out.match(/✖/g) || []).length;
  console.log(`${label.padEnd(52)} exit=${res.status} failing_assertions=${fails}`);
  return res.status !== 0;
}

const checks = [
  [
    'baseline (unmodified) must PASS',
    original,
    false,
  ],
  [
    'token step given --provenance must FAIL',
    original.replace(
      'run: npm publish --access public --tag latest',
      'run: npm publish --access public --provenance --tag latest',
    ),
    true,
  ],
  [
    'token step loses --tag latest must FAIL',
    original.replace(
      'run: npm publish --access public --tag latest',
      'run: npm publish --access public',
    ),
    true,
  ],
  [
    'OIDC step loses --provenance must FAIL',
    original.replace(
      'run: npm publish --access public --provenance --tag latest',
      'run: npm publish --access public --tag latest',
    ),
    true,
  ],
  [
    'both steps lose --tag latest must FAIL',
    original.replace(/--tag latest/g, ''),
    true,
  ],
  [
    'use_token_fallback default flipped to true must FAIL',
    original.replace(
      '        required: false\n        default: false\n        type: boolean',
      '        required: false\n        default: true\n        type: boolean',
    ),
    true,
  ],
  [
    'node-version dropped to 22 must FAIL',
    original.replace('node-version: "24"', 'node-version: "22"'),
    true,
  ],
  [
    'regex npm gate reintroduced in the workflow must FAIL',
    original.replace(
      '          node -e "\n            const parse =',
      '          if [[ "$(npm --version)" =~ ^11\\.(5[1-9]|[6-9][0-9])\\.|^1[2-9]\\. ]]; then echo ok; fi\n          node -e "\n            const parse =',
    ),
    true,
  ],
  [
    'token env removed from the token step must FAIL',
    original.replace(
      '          NODE_AUTH_TOKEN: ${{ secrets.NPM_TOKEN }}',
      '          SOME_OTHER: ${{ secrets.NPM_TOKEN }}',
    ),
    true,
  ],
  [
    'fail-closed exit removed must FAIL',
    original.replace(
      '            exit 1\n          fi\n          echo "NPM_TOKEN is present',
      '            echo "would fail"\n          fi\n          echo "NPM_TOKEN is present',
    ),
    true,
  ],
  [
    'continue-on-error added to a step must FAIL',
    original.replace(
      '      - name: Publish to npm with the NPM_TOKEN secret',
      '      - name: Publish to npm with the NPM_TOKEN secret\n        continue-on-error: true',
    ),
    true,
  ],
  [
    'existence gate removed must FAIL',
    original.replace('Check whether this version already exists on the registry', 'Removed'),
    true,
  ],
];

let ok = true;
try {
  for (const [label, mutated, shouldFail] of checks) {
    const failed = run(label, mutated);
    const correct = failed === shouldFail;
    if (!correct) ok = false;
    console.log(`   -> ${correct ? 'CORRECT' : 'INCORRECT (control is broken!)'}`);
  }
} finally {
  fs.writeFileSync(wf, original, 'utf8');
}

console.log(ok ? '\nALL CONTROLS CORRECT' : '\nSOME CONTROLS WRONG');
process.exit(ok ? 0 : 1);