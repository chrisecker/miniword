System Instructions / Guidelines
1. Language & Style

* Language: Always use English for code, variable names, and documentation.
* Conciseness: Write code in a minimalist, concise style. Avoid boilerplate.
* Formatting: Use exactly one space before and after assignment operators (e.g., x = 1).
* Comments: Add comments only if they are essential for understanding complex logic.

2. Naming Conventions

* Case: Use snake_case (lowercase with underscores) for all variables and methods.
* Pattern: Name functions and methods using the two part "verb_noun" pattern (e.g., get_data, render_tree).

3. Architecture & Constraints

* Modularity: Keep individual .py files as independent as possible.
* Core Libraries: The modules textmodel and texeltree are external dependencies. Do not extend or modify them.
* Exclusions:
* Ignore all files and directories prefixed with dev_ (drafts only).
   * Ignore the file test/moby.txl.

4. Testing & Workflow

* Automated Tests: Run via runtests.py.
* Module test: python runtests.py path/to/file.py
   * Specific test: python runtests.py path/to/file.py test_name
* Manual Demos: Functions named demo_XX (e.g., demo_00) are manual tests intended for human execution, not for automated test suites.
* Full Suite: Use python test_all to invoke all tests.
* Requirement: All tests must pass before any commit or final delivery.

4. Code Quality: The Boy Scout Rule
Every session should improve the codebase, not just add to it. Actively refactor code you encounter, even outside your immediate task scope.

- **Don't Repeat Yourself (Rule of Three):** Consolidate duplicate patterns into reusable functions only after the 3rd occurrence. Do not abstract prematurely.
- **Hygiene:** Delete dead code immediately (unused imports, functions, variables, commented code). If it's not running, it goes.
- **Leverage:** Use battle-tested packages over custom implementations. Do not reinvent the wheel unless the wheel is broken.
- **Readable:** Code must be self-documenting. Comments should explain *why*, not *what*.
- **Safety:** If a refactor carries high risk of breaking functionality, flag it for user review rather than applying it silently.

5. Persistent Context & Memory
Since our context resets between sessions, we use files to track our brain.

**The Dev Log (`DEVLOG.md`)**
At the completion of a task, you must check if `DEVLOG.md` exists. If so, propose an append summarizing:
1. **The Change:** High-level summary of files touched.
2. **The Reasoning:** Why we made specific structural decisions.
3. **The Tech Debt:** Any corners we cut that need to be fixed later.

**Goal:** If a new developer (or a new AI session) joins tomorrow, they should be able to read `DEVLOG.md` and understand the state of the project immediately.

**Operational Rule**
- After every interaction that includes a code change, you must append an entry to `DEVLOG.md` before finishing. Do not just suggest it. If you truly cannot write to the file (permissions/conflicts), provide the exact snippet the next person should paste. This is mandatory and should be treated as a checklist item for every task.
