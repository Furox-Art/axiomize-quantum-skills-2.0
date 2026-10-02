name: Feature request
title: "[FEATURE] "
description: Propose a capability the project does not have yet
labels: ["enhancement"]
body:
  **The problem**

  <!-- Describe the situation you are in, not the solution you want. What are you trying to do
       that is hard or impossible today? -->

  **What you tried**

  <!-- What have you already attempted? Including a workaround you built is useful context. -->

  **The change you would like**

  <!-- Sketch it. If it touches a public interface (CLI flag, Model IR field, MCP tool, REST
       route, or a file under docs/), say which. -->

  **Scope check**

  This project tries to keep the trust boundary small: untrusted input is parsed through a
  restricted grammar, expensive work needs approval, and generated code is never an OS
  sandbox. Please say which parts of your request touch that boundary, if any.

  **Alternatives you considered**

  <!-- Including "none, this is the whole point". -->

  **Checklist**

  - [ ] I searched existing issues for this.
  - [ ] This is not a security report. For vulnerabilities, see SECURITY.md.