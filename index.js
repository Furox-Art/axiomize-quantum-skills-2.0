'use strict';

// Thin launcher for the Axiomize Python engine.
//
// Two bugs are fixed here relative to the previous revision, both of which made
// `npx axiomize-quantum` unusable:
//
//   1. Syntax error. The old body was `proc.on('close', (code) =; }`, which is
//      not valid JavaScript, so `node --check` failed and every invocation died
//      with `SyntaxError: Unexpected token ';'` before running anything.
//   2. Wrong module target. It spawned `python -m axiomize_quantum.cli`, a
//      module that does not exist anywhere in this repository. The import
//      package is `axiomize` (see `[project]` in pyproject.toml) and its CLI
//      module is `axiomize.cli`, which defines `main()` and a `__main__` guard.
//
// The exit code of the child is propagated so that shell callers, CI steps and
// the npm contract test can all trust `process.exitCode`.

const { spawn } = require('node:child_process');

// `python` on Windows, `python3` elsewhere. Honour an explicit override first so
// CI and virtualenv users are not at the mercy of PATH ordering.
function resolvePython() {
  const override = process.env.AXIOMIZE_PYTHON;
  if (override) {
    return override;
  }
  return process.platform === 'win32' ? 'python' : 'python3';
}

// The console-script equivalent is `axiomize`, installed by the wheel. Prefer it
// when it is on PATH: it is the entry point the packaging metadata actually
// declares, so using it keeps this launcher honest about what users get.
function resolveEntryPoint() {
  if (process.env.AXIOMIZE_CLI) {
    return { command: process.env.AXIOMIZE_CLI, args: [] };
  }
  return { command: resolvePython(), args: ['-m', 'axiomize.cli'] };
}

function runAxiomizeQuantum(args) {
  const { command, args: prefix } = resolveEntryPoint();
  const child = spawn(command, [...prefix, ...args], {
    stdio: 'inherit',
    cwd: __dirname,
  });

  child.on('error', (err) => {
    process.stderr.write(
      `axiomize-quantum: failed to launch '${command}': ${err.message}\n` +
        'Install the Python package first: pip install axiomize-quantum-skills-2.0\n',
    );
    process.exitCode = 127;
  });

  child.on('close', (code, signal) => {
    if (signal) {
      process.stderr.write(`axiomize-quantum: terminated by signal ${signal}\n`);
      process.exitCode = 128;
      return;
    }
    process.exitCode = code === null ? 1 : code;
  });

  return child;
}

module.exports = { runAxiomizeQuantum, resolvePython, resolveEntryPoint };

if (require.main === module) {
  runAxiomizeQuantum(process.argv.slice(2));
}
