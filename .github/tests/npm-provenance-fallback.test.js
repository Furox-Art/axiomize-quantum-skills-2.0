'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { test } = require('node:test');

const workflow = fs.readFileSync(
  path.join(__dirname, '..', 'workflows', 'npm-publish.yml'), 'utf8'
);

test('OIDC publishing opts into provenance', () => {
  assert.match(workflow, /run: npm publish --access public --provenance --tag latest/);
});

test('token fallback explicitly opts out of OIDC provenance', () => {
  assert.match(
    workflow,
    /name: Publish to npm with the NPM_TOKEN secret[\s\S]*?run: npm publish --access public --no-provenance --tag latest/
  );
});
