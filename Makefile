.PHONY: install test lint api worker migrate evaluate-baseline
install:
	python -m pip install -r requirements.lock
	python -m pip install --no-deps -e .
test:
	pytest -q --junitxml=evals/results/pytest.xml
lint:
	ruff check src tests scripts
	ruff format --check src tests scripts
migrate:
	agentproof migrate
api:
	agentproof api
worker:
	agentproof worker
evaluate-baseline:
	python scripts/evaluate.py --suite support --mode baseline --output evals/results/support-baseline.json
