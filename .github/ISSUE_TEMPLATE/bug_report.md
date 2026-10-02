name: Bug report
title: "[BUG] "
description: Something in the engine, tools, or skills behaves incorrectly
labels: ["bug", "documentation"]
body:
  <!-- Thanks for taking the time. A minimal reproduction is worth more than a long description. -->

  **What happened?**

  <!-- The wrong behaviour, in one or two sentences. -->

  **Reproduction**

  <!-- The smallest thing that shows the problem. For the engine, a command that fails is ideal:
       axiomize ... , or the exact JSON payload you sent to /model, /solve or an MCP tool. -->

  ```text
  paste the command and its output here
  ```

  **Expected behaviour**

  <!-- What you expected instead, and which rule in the docs says so. Quote it if you can:
       SKILL.md, docs/tutorial.md, docs/integrations.md, or the skill contract in CONTRIBUTING.md. -->

  **Environment**

  | | |
  |---|---|
  | axiomize version | <!-- pip show axiomize-quantum-skills-2.0 --> |
  | commit | <!-- git rev-parse HEAD, if built from source --> |
  | Python | <!-- python -V --> |
  | OS | |
  | backends | <!-- paste the output of: axiomize tools --> |
  | interface | <!-- CLI / MCP / REST, and which subcommand or tool --> |
  | agent runtime | <!-- if the bug is in a skill: Claude Code, opencode, other --> |

  **Anything else**

  <!-- Smaller repro, logs, a failing test, or the doc sentence that is wrong. -->