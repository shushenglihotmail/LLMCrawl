.PHONY: build dev test clean up down logs install-dev setup-dev dev-up dev-down dev-logs pre-commit

# Development Environment Setup
install-dev:
	pip install -r requirements/dev.txt

setup-dev:
	python scripts/setup_dev.py

setup-dev-windows:
	powershell -ExecutionPolicy Bypass -File scripts/setup_dev.ps1

quick-start:
	bash scripts/start_dev.sh

quick-start-windows:
	powershell -ExecutionPolicy Bypass -File scripts/start_dev.ps1

# Docker operations (from deploy folder)
up:
	cd deploy && docker-compose -f docker-compose.dev.yml up -d
	@echo "Services are running!"
	@echo "Gateway: http://localhost:8000"
	@echo "Crawler: http://localhost:8001"
	@echo "Indexer: http://localhost:8002"
	@echo "Memory Service: http://localhost:8007"
	@echo "Qdrant Dashboard: http://localhost:6333/dashboard"

down:
	cd deploy && docker-compose -f docker-compose.dev.yml down

logs:
	cd deploy && docker-compose -f docker-compose.dev.yml logs -f

rebuild:
	cd deploy && docker-compose -f docker-compose.dev.yml up -d --build

build:
	cd deploy && docker-compose -f docker-compose.dev.yml build --no-cache

# Development shortcuts (aliases for up/down/logs)
dev: dev-up

dev-up:
	cd deploy && docker-compose -f docker-compose.dev.yml up -d
	@echo "Services are running!"
	@echo "Gateway: http://localhost:8000"
	@echo "Crawler: http://localhost:8001"
	@echo "Indexer: http://localhost:8002"
	@echo "Memory Service: http://localhost:8007"
	@echo "Qdrant Dashboard: http://localhost:6333/dashboard"

dev-down:
	cd deploy && docker-compose -f docker-compose.dev.yml down

dev-logs:
	cd deploy && docker-compose -f docker-compose.dev.yml logs -f

# Testing
test:
	cd deploy && docker-compose -f docker-compose.dev.yml exec gateway python -m pytest tests/ -v
	cd deploy && docker-compose -f docker-compose.dev.yml exec crawler python -m pytest tests/ -v
	cd deploy && docker-compose -f docker-compose.dev.yml exec indexer python -m pytest tests/ -v

test-dev:
	pytest tests/ -v --cov=. --cov-report=html

test-integration:
	python tests/integration/test_end_to_end.py

# Code quality
pre-commit:
	pre-commit run --all-files

lint:
	cd deploy && docker-compose -f docker-compose.dev.yml exec gateway python -m black . --check
	cd deploy && docker-compose -f docker-compose.dev.yml exec gateway python -m isort . --check-only
	cd deploy && docker-compose -f docker-compose.dev.yml exec gateway python -m flake8 .

format:
	cd deploy && docker-compose -f docker-compose.dev.yml exec gateway python -m black .
	cd deploy && docker-compose -f docker-compose.dev.yml exec gateway python -m isort .

# Database operations
db-reset:
	cd deploy && docker-compose -f docker-compose.dev.yml down -v
	cd deploy && docker-compose -f docker-compose.dev.yml up -d qdrant postgres redis

# Monitoring and Metrics
monitoring-up:
	cd deploy && docker-compose -f docker-compose.dev.yml --profile monitoring up -d
	@echo "Monitoring stack started!"
	@echo "Prometheus: http://localhost:9090"
	@echo "Grafana: http://localhost:3001 (admin/admin)"
	@echo "Qdrant Dashboard: http://localhost:6333/dashboard"

monitoring-down:
	cd deploy && docker-compose -f docker-compose.dev.yml stop prometheus grafana

metrics:
	@echo "Opening monitoring dashboards..."
	@echo "Prometheus: http://localhost:9090"
	@echo "Grafana: http://localhost:3001"

metrics-gateway:
	curl http://localhost:8000/metrics

metrics-crawler:
	curl http://localhost:8001/metrics

metrics-indexer:
	curl http://localhost:8002/metrics

metrics-memory:
	curl http://localhost:8007/metrics

metrics-all:
	@echo "=== Gateway Metrics ==="
	@curl -s http://localhost:8000/metrics | grep "http_requests_total"
	@echo "\n=== Crawler Metrics ==="
	@curl -s http://localhost:8001/metrics | grep "http_requests_total"
	@echo "\n=== Indexer Metrics ==="
	@curl -s http://localhost:8002/metrics | grep "http_requests_total"
	@echo "\n=== Memory Metrics ==="
	@curl -s http://localhost:8007/metrics | grep "http_requests_total"

# Cleanup
clean:
	cd deploy && docker-compose -f docker-compose.dev.yml down -v --remove-orphans
	docker system prune -f
	docker volume prune -f

# Health checks (cross-platform)
ifeq ($(OS),Windows_NT)
health:
	@powershell -ExecutionPolicy Bypass -File scripts/health_check.ps1
else
health:
	@bash scripts/health_check.sh
endif

health-gateway:
	@curl -s http://localhost:8000/health | python -m json.tool 2>/dev/null || echo "Service not available"

health-crawler:
	@curl -s http://localhost:8001/health | python -m json.tool 2>/dev/null || echo "Service not available"

health-indexer:
	@curl -s http://localhost:8002/health | python -m json.tool 2>/dev/null || echo "Service not available"

health-memory:
	@curl -s http://localhost:8007/health | python -m json.tool 2>/dev/null || echo "Service not available"

# Example queries
test-query:
	curl -X POST http://localhost:8000/chat \
		-H "Content-Type: application/json" \
		-d '{"message": "What are the latest NVDA earnings?"}'

stream-test:
	curl -X POST http://localhost:8000/chat \
		-H "Content-Type: application/json" \
		-d '{"message": "Latest Tesla news?", "stream": true}'
