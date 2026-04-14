.PHONY: install install-frontend install-backend dev dev-frontend dev-backend \
        test lint lint-python lint-frontend format format-python format-frontend \
        typecheck build clean formula-sha

# ── Install ───────────────────────────────────────────────────────────────────

install: install-frontend install-backend

install-frontend:
	npm install

install-backend:
	cd agent && python -m venv .venv && .venv/bin/pip install -e ".[dev]"

# ── Dev servers ───────────────────────────────────────────────────────────────
# Runs all three services (Astro, agent, semantic) in the foreground.
# Prefer ./start.sh for coloured output; this target exists for CI/scripting.

dev:
	./start.sh

dev-frontend:
	npm run dev

dev-backend:
	cd agent && .venv/bin/uvicorn app:app --host 0.0.0.0 --port 8001 --reload

dev-semantic:
	cd agent && .venv/bin/python semantic_server.py

# ── Tests ─────────────────────────────────────────────────────────────────────

test: test-backend

test-backend:
	cd agent && .venv/bin/pytest

test-frontend:
	npm run test

# ── Lint ──────────────────────────────────────────────────────────────────────

lint: lint-python lint-frontend

lint-python:
	cd agent && .venv/bin/ruff check .

lint-frontend:
	npm run lint

# ── Format ───────────────────────────────────────────────────────────────────

format: format-python format-frontend

format-python:
	cd agent && .venv/bin/ruff format .

format-frontend:
	npm run format

# ── Type checking ─────────────────────────────────────────────────────────────

typecheck:
	npm run typecheck

# ── Build ─────────────────────────────────────────────────────────────────────

build:
	npm run build

# ── Clean ─────────────────────────────────────────────────────────────────────

clean:
	rm -rf dist/ .astro/ agent/__pycache__ agent/.pytest_cache agent/.coverage

# ── Homebrew formula maintenance ──────────────────────────────────────────────
# Prints the sha256 of the GitHub release tarball for a given tag (default: the
# version declared in agent/pyproject.toml).  Use the output to update the
# sha256 line in Formula/phoenix.rb when cutting a new release.
#
# Usage:
#   make formula-sha                  # uses version from pyproject.toml
#   make formula-sha TAG=v5.1.0       # override tag

formula-sha:
	$(eval TAG ?= v$(shell grep '^version' agent/pyproject.toml | head -1 | sed 's/.*"\(.*\)"/\1/'))
	@echo "Computing sha256 for tag $(TAG)…"
	@curl -sL "https://github.com/omkar-dev/phoenix/archive/refs/tags/$(TAG).tar.gz" \
	  | shasum -a 256 | awk '{print $$1}'

formula-sha:
	@echo "Computing sha256 for tag $(TAG)…"
	@curl -sL "https://github.com/omkar-dev/phoenix/archive/refs/tags/$(TAG).tar.gz" \
	  | shasum -a 256 | awk '{print $$1}'
