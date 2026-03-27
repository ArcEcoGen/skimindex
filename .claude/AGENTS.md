# AGENTS.md

This file documents the project's coding standards, build/test/lint commands, and operational guidelines for agentic AI assistants.

## Build, Lint, and Test Commands

- **Rust**: `cargo build --all-targets && cargo test --all-targets`
- **Go**: `go build ./... && go vet ./... && go test ./...`
- **Python**: `python -m pytest tests/` (single test: `python -m pytest tests/test_module.py::test_function`)
- **R**: `Rscript -e "devtools::test()"` (single test: `Rscript -e "testthat::test_file('tests/testthat/test_module.R')"`)
- **Bash**: Run tests directly or use `bash -n script.sh` for syntax check

For all languages: run linters before committing (see hooks in `.claude/hooks/`)

## Code Style Guidelines

### General Principles
- Follow language-specific idioms and conventions
- Prioritize readability over cleverness
- Use descriptive names for variables, functions, and types
- Keep functions small and focused on a single responsibility

### Imports and Dependencies
- **Rust**: Use `use` statements at top of file; group std, external crates, and local modules
- **Go**: Import blocks organized: standard library, then external packages, then local packages
- **Python**: Standard library imports first, then third-party, then local imports
- **R**: Attach packages with `library()` at top of script; use `pkg::function()` for occasional calls
- **Bash**: Source local modules with absolute paths or relative from script location

### Naming Conventions
- **Rust**: Types/CamelCase, functions/snake_case, constants/SCREAMING_SNAKE_CASE
- **Go**: Exported names start with uppercase, unexported with lowercase; use CamelCase for acronyms
- **Python**: Classes/CamelCase, functions/variables/snake_case; use _private for internal
- **R**: Functions/lowercase_with_underscores; avoid naming conflicts with base R functions
- **Bash**: Functions/snake_case; variables lowercase; constants UPPERCASE

### Error Handling
- **Rust**: Use `Result<T, E>` and `?` operator; define custom error types for libraries
- **Go**: Return `(result, error)` tuple; handle errors immediately after function call
- **Python**: Raise specific exception types; catch only what you can handle meaningfully
- **R**: Use `stop()` for errors, `warning()` for warnings; consider tryCatch for recovery
- **Bash**: Check return codes with `$?`; use `set -e` for strict error handling

### Types and Documentation
- **Rust**: Specify all types explicitly; use `cargo doc` for documentation
- **Go**: Document exported functions with comments; use type aliases for clarity
- **Python**: Use type hints (PEP 484); docstrings with Google or NumPy style
- **R**: Use roxygen2 for function documentation; document all exported functions
- **Bash**: Comment complex logic; use `set -x` for debugging trace

## Cursor Rules

- Run linters after any file write (see `.claude/hooks/post-write-lint.sh`)
- For Rust/Go projects, run `cargo clippy` or `go vet` before committing
- Verify tests pass after changes: `cargo test`, `go test`, `pytest`
- When modifying multiple files, run full test suite before finalizing

## Copilot Rules

- Delegation: Use Qwen3-Coder for atomic tasks via MCP server at port 1248
- Code review: Invoke code-reviewer agent for PRs and significant changes
- Planning: Use task-planner to break complex tasks into atomic steps
- Always verify agent outputs before committing or pushing

## Hooks and Automation

- **post-write-lint.sh**: Runs linters after file writes
- **subagent-stop-log.sh**: Logs subagent completion and exit codes
- **pre-bash-guard.sh**: Validates bash scripts before execution

## MCP Server Configuration

- **Endpoint**: `http://localhost:1248`
- **Model**: `qwen/qwen3-coder-next`
- **Local agent loop**: `.claude/mcp/qwen3-mcp/agent_lm.py`
- **Server script**: `.claude/mcp/qwen3-mcp/server.py`

## Project Structure

- `.claude/agents/` - Agent definitions (qwen3-worker, code-reviewer, task-planner)
- `.claude/skills/` - Domain-specific skills and conventions
- `.claude/hooks/` - Git hooks for automated checks
- `.claude/mcp/qwen3-mcp/` - MCP server and agent integration

## Testing Strategy

- Run tests after any code change
- For single test execution, use language-specific commands above
- CI/CD should run full test suite on every push
- Code coverage targets: 80% minimum for production code
