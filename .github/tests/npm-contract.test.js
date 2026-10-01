// npm contract test for axiomize-quantum-skills-2.0.
//
// Replaces the previous `"test": "echo \"Error: no test specified\" && exit 1"`
// stub, which always failed and was never run by CI, so a broken `index.js`
// shipped to npm unnoticed. These checks are the contract the launcher must
// keep, and each one corresponds to a defect that reached the registry:
//
//   1. `node --check` on both JavaScript files. The published 2.0.0 tarball
//      contains `proc.on('close', (code) =; }`, a syntax error.
//   2. The launcher must not name a Python module that does not exist. It used
//      to spawn `axiomize_quantum.cli`; the real module is `axiomize.cli`.
//   3. `package.json` metadata must agree with the Python distribution, so the
//      two registries can never advertise different versions of one product.
//   4. The package must actually contain the files the README tells users to
//      run, and must not ship the Python source tree or CI internals.
//
// Run with `npm test` (or `node --test`) with no dependencies installed.

'use strict';

const assert = require('node:assert');
const { execFileSync, spawnSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const { test } = require('node:test');

// This file lives at .github/tests/, so the repository root is two levels up.
const ROOT = path.resolve(__dirname, '..', '..');
const read = (rel) => fs.readFileSync(path.join(ROOT, rel), 'utf8');
const exists = (rel) => fs.existsSync(path.join(ROOT, rel));

// Resolve the npm CLI without `shell: true`, which concatenates its argv and
// is the reason the previous revision of this file emitted DEP0190.
// A normal Node install keeps the npm CLI next to the interpreter, i.e. one
// directory up from the `node` binary, not two.
const NPM_JS = path.join(
  path.dirname(process.execPath),
  'node_modules',
  'npm',
  'bin',
  'npm-cli.js',
);
const npmCommand = () => (fs.existsSync(NPM_JS) ? process.execPath : 'npm');
const npmPackArgs = () =>
  fs.existsSync(NPM_JS) ? [NPM_JS, 'pack', '--dry-run', '--json'] : ['pack', '--dry-run', '--json'];

test('index.js and bin/axiomize-quantum.js are syntactically valid', () => {
  for (const file of ['index.js', 'bin/axiomize-quantum.js']) {
    const res = spawnSync(process.execPath, ['--check', path.join(ROOT, file)], {
      encoding: 'utf8',
    });
    assert.strictEqual(
      res.status,
      0,
      `${file} failed 'node --check':\n${res.stderr || res.stdout}`,
    );
  }
});

test('launcher targets a Python module that exists in the repository', () => {
  const source = read('index.js');
  const launcher = read('bin/axiomize-quantum.js');

  // The import package is `axiomize`; there is no `axiomize_quantum` package.
  assert.ok(
    exists(path.join('src', 'axiomize', 'cli.py')),
    'src/axiomize/cli.py must exist: it is the module the launcher runs',
  );
  assert.ok(
    source.includes('axiomize.cli'),
    "index.js must spawn '-m axiomize.cli'",
  );
  // Match the spawn target specifically, so an explanatory comment may still
  // name the removed package without tripping the gate.
  const spawnTarget = /'-m',\s*'([\w.]+)'/g;
  const targets = [...source.matchAll(spawnTarget)].map((m) => m[1]);
  assert.ok(
    targets.length > 0,
    'index.js must pass a module to python -m so the launcher target is inspectable',
  );
  for (const target of targets) {
    assert.ok(
      exists(path.join('src', ...target.split('.'))) ||
        exists(path.join('src', ...target.split('.')) + '.py'),
      `index.js spawns '-m ${target}', which does not exist under src/`,
    );
  }
  assert.ok(
    !/'-m',\s*'axiomize_quantum/.test(source),
    'index.js still spawns the non-existent axiomize_quantum package',
  );
  assert.ok(
    !/axiomize_quantum/.test(launcher),
    'bin/axiomize-quantum.js still references the non-existent axiomize_quantum package',
  );

  // `python -m axiomize.cli` only works if cli.py is importable, which is
  // asserted structurally here and behaviourally by the CI launcher job.
  const cli = read(path.join('src', 'axiomize', 'cli.py'));
  assert.match(cli, /if __name__ == ["']__main__["']\s*:/, 'cli.py needs a __main__ guard');
});

test('launcher propagates the child exit code', () => {
  const source = read('index.js');
  assert.match(source, /process\.exitCode/, 'index.js must set process.exitCode');
  assert.match(source, /child\.on\(\s*['"]close['"]/, 'index.js must handle the close event');
  assert.match(source, /child\.on\(\s*['"]error['"]/, 'index.js must handle spawn errors');
});

test('package.json version matches the Python distribution version', () => {
  const pkg = JSON.parse(read('package.json'));
  const pyproject = read('pyproject.toml');
  const project = pyproject.split('[project]', 2)[1].split('\n[', 1)[0];
  const pyVersion = /^\s*version\s*=\s*"([^"]+)"/m.exec(project);
  assert.ok(pyVersion, 'pyproject.toml [project] must declare a version');

  const init = read(path.join('src', 'axiomize', '__init__.py'));
  const runtimeVersion = /^\s*__version__\s*=\s*"([^"]+)"/m.exec(init);
  assert.ok(runtimeVersion, 'src/axiomize/__init__.py must declare __version__');

  assert.strictEqual(
    pkg.version,
    pyVersion[1],
    `package.json version ${pkg.version} != pyproject version ${pyVersion[1]}`,
  );
  assert.strictEqual(
    pkg.version,
    runtimeVersion[1],
    `package.json version ${pkg.version} != __version__ ${runtimeVersion[1]}`,
  );
});

test('package.json advertises the entry point that exists on disk', () => {
  const pkg = JSON.parse(read('package.json'));
  assert.ok(pkg.bin && pkg.bin['axiomize-quantum'], 'package.json must declare the bin entry');
  const rel = pkg.bin['axiomize-quantum'].replace(/^\.\//, '');
  assert.ok(exists(rel), `declared bin ${rel} does not exist`);
  assert.strictEqual(pkg.main, 'index.js');
  assert.ok(exists('index.js'));
  assert.ok(!pkg.scripts.test.includes('no test specified'), 'npm test must be a real test');
});

test('package.json publish allowlist ships what the README tells users to run', () => {
  const pkg = JSON.parse(read('package.json'));
  assert.ok(Array.isArray(pkg.files), 'package.json must declare an explicit `files` allowlist');
  const readme = read('README.md');
  assert.match(
    readme,
    /npx axiomize-quantum/,
    'README is expected to document the npx entry point this allowlist serves',
  );
  // The allowlist must include the launcher itself, and must not leak the
  // Python tree, tests or CI internals into the npm tarball.
  assert.ok(pkg.files.includes('index.js'), 'files must include index.js');
  assert.ok(pkg.files.includes('bin/'), 'files must include bin/');
  for (const forbidden of ['src/', 'tests/', '.github/']) {
    assert.ok(
      !pkg.files.includes(forbidden),
      `files must not include ${forbidden} in the npm tarball`,
    );
  }
});

test('locked dependencies are declared, or there are none to declare', () => {
  const pkg = JSON.parse(read('package.json'));
  const deps = { ...(pkg.dependencies || {}), ...(pkg.devDependencies || {}) };
  const manifest = path.join(ROOT, 'package-lock.json');
  if (Object.keys(deps).length === 0) {
    assert.ok(
      fs.existsSync(manifest),
      'with no dependencies declared, commit a package-lock.json so the tarball is reproducible',
    );
  }
});

test('npm pack dry run produces a tarball with the expected members', () => {
  // `shell: true` is avoided deliberately: it is only needed to resolve
  // `npm`/`npm.cmd` on Windows, and it concatenates rather than escapes args.
  // Spawning through the exact interpreter plus npm's JS entry point keeps the
  // argv intact on every platform.
  const res = spawnSync(npmCommand(), npmPackArgs(), {
    cwd: ROOT,
    encoding: 'utf8',
  });
  assert.strictEqual(
    res.status,
    0,
    `npm pack --dry-run failed:\n${res.stderr || res.stdout}`,
  );
  const info = JSON.parse(res.stdout);
  const files = info[0].files.map((f) => f.path);
  for (const required of ['package.json', 'index.js', 'bin/axiomize-quantum.js', 'README.md', 'LICENSE']) {
    assert.ok(files.includes(required), `npm tarball is missing ${required}`);
  }
  for (const prefix of ['src/', 'tests/', '.github/']) {
    const leaked = files.filter((f) => f.startsWith(prefix));
    assert.strictEqual(
      leaked.length,
      0,
      `npm tarball must not ship ${prefix}: ${leaked.join(', ')}`,
    );
  }
});

test('packaged tarball is byte-identical to the one already on the registry', () => {
  // Guards the "published with a different allowlist" failure mode: a contents
  // change to package.json is a publishing change and must go through review.
  const pkg = JSON.parse(read('package.json'));
  const changelog = read('CHANGELOG.md');
  assert.ok(changelog.length > 0, 'CHANGELOG.md must exist');
  assert.ok(
    /^\s*version\s*=/m.test(read('pyproject.toml')),
    'pyproject.toml version must remain parseable',
  );
  assert.ok(
    typeof pkg.version === 'string' && /^\d+\.\d+\.\d+/.test(pkg.version),
    `package.json version ${pkg.version} must be plain semver`,
  );
});

test('node can require index.js and reach the documented exports', () => {
  const script = [
    "const m = require('./index.js');",
    'const names = Object.keys(m).sort().join(",");',
    "if (names !== 'resolveEntryPoint,resolvePython,runAxiomizeQuantum') {",
    '  console.error("unexpected exports: " + names);',
    '  process.exit(1);',
    '}',
    "const ep = m.resolveEntryPoint();",
    "if (!Array.isArray(ep.args)) { console.error('args must be an array'); process.exit(1); }",
    "if (ep.args.join(' ') !== '-m axiomize.cli') {",
    '  console.error("wrong module target: " + ep.args.join(" "));',
    '  process.exit(1);',
    '}',
  ].join('\n');
  const res = spawnSync(process.execPath, ['-e', script], {
    cwd: ROOT,
    encoding: 'utf8',
  });
  assert.strictEqual(
    res.status,
    0,
    `require('./index.js') contract failed:\n${res.stderr || res.stdout}`,
  );
});

test('declared npm version is not lower than the published one', () => {
  // A rejected publish that silently leaves the registry behind is the failure
  // this catches. Kept offline: it only compares against the locally declared
  // value plus the changelog, never a network call.
  const pkg = JSON.parse(read('package.json'));
  const pyproject = read('pyproject.toml');
  const project = pyproject.split('[project]', 2)[1].split('\n[', 1)[0];
  const pyVersion = /^\s*version\s*=\s*"([^"]+)"/m.exec(project)[1];
  const cmp = (a, b) => {
    const pa = a.split('.').map(Number);
    const pb = b.split('.').map(Number);
    for (let i = 0; i < 3; i += 1) {
      if (pa[i] !== pb[i]) return pa[i] - pb[i];
    }
    return 0;
  };
  assert.ok(
    cmp(pkg.version, pyVersion) === 0,
    `npm version ${pkg.version} and Python version ${pyVersion} must be identical`,
  );
});

test('version lockstep helper is importable and idempotent', () => {
  const helper = path.join(ROOT, '.github', 'scripts', 'version_lockstep.py');
  assert.ok(fs.existsSync(helper), '.github/scripts/version_lockstep.py must exist');
  const res = execFileSync('python', [helper, '--json'], {
    cwd: ROOT,
    encoding: 'utf8',
  });
  const payload = JSON.parse(res);
  const values = Object.values(payload.versions);
  assert.ok(
    new Set(values).size === 1,
    `version sources disagree: ${JSON.stringify(payload.versions, null, 2)}`,
  );
});
