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

