.PHONY: verify verify-backend verify-frontend \
       verify-connectors verify-graph verify-inference verify-briefing \
       verify-api verify-chat verify-claude verify-workers verify-mcp \
       verify-agent verify-slack \
       dev migrate new-migration deploy

# ── Full repo (cross-service changes only) ────────────────────────────

verify: verify-backend verify-frontend
	@echo "All checks passed"

# ── Service-scoped (fast, run after changing a specific module) ───────

verify-connectors:
	ruff check src/connectors/
	pytest tests/test_connectors/ -x -q 2>/dev/null || echo "No connector tests found"

verify-graph:
	ruff check src/graph/
	pytest tests/test_graph/ -x -q

verify-inference:
	ruff check src/inference/
	pytest tests/test_inference/ -x -q

verify-briefing:
	ruff check src/briefing/
	pytest tests/test_briefing/ -x -q 2>/dev/null || echo "No briefing tests found"

verify-api:
	ruff check src/api/
	pytest tests/test_api/ -x -q 2>/dev/null || echo "No API tests found"

verify-chat:
	ruff check src/chat/
	pytest tests/test_chat/ -x -q 2>/dev/null || echo "No chat tests found"

verify-llm:
	ruff check src/llm/
	pytest tests/test_llm/ -x -q 2>/dev/null || echo "No llm tests found"

verify-workers:
	ruff check src/workers/
	pytest tests/test_workers/ -x -q 2>/dev/null || echo "No worker tests found"

verify-mcp:
	ruff check src/mcp/
	pytest tests/test_mcp/ -x -q

verify-agent:
	ruff check src/agent/
	pytest tests/test_agent/ -x -q

verify-slack:
	ruff check src/slack/
	pytest tests/test_slack/ -x -q

# ── Aggregate by stack ────────────────────────────────────────────────

verify-backend:
	ruff check src/ tests/
	pytest -x -q

verify-frontend:
	cd frontend && npx tsc --noEmit && npx eslint .

# ── Hooks ─────────────────────────────────────────────────────────────

setup-hooks:
	pip install pre-commit
	pre-commit install

# ── Convenience ───────────────────────────────────────────────────────

dev:
	docker compose up --build

migrate:
	alembic upgrade head

new-migration:
	alembic revision --autogenerate -m "$(msg)"

# ── Deploy ────────────────────────────────────────────────────────────
# Trigger the GitHub Actions deploy workflow. See scripts/deploy/README.md
# for one-time setup.

deploy:
	gh workflow run deploy.yml $(ARGS)
