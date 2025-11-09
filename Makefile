.PHONY: build dev test clean up down logs

# Docker operations
build:
	docker-compose build --no-cache

up:
	docker-compose up -d

down:
	docker-compose down

logs:
	docker-compose logs -f

# Development
dev:
	docker-compose -f docker-compose.yml -f docker-compose.dev.yml up

test:
	docker-compose exec gateway python -m pytest tests/ -v
	docker-compose exec crawler python -m pytest tests/ -v
	docker-compose exec indexer python -m pytest tests/ -v

test-integration:
	python tests/integration/test_end_to_end.py

# Linting and formatting
lint:
	docker-compose exec gateway python -m black . --check
	docker-compose exec gateway python -m isort . --check-only
	docker-compose exec gateway python -m flake8 .

format:
	docker-compose exec gateway python -m black .
	docker-compose exec gateway python -m isort .

# Database operations
db-reset:
	docker-compose down -v
	docker-compose up -d qdrant postgres redis

# Monitoring
metrics:
	open http://localhost:9090  # Prometheus
	open http://localhost:3000  # Grafana

# Cleanup
clean:
	docker-compose down -v --remove-orphans
	docker system prune -f
	docker volume prune -f

# Health checks
health:
	@echo "Checking service health..."
	@curl -s http://localhost:8000/health | jq .
	@curl -s http://localhost:8001/health | jq .
	@curl -s http://localhost:8002/health | jq .

# Example queries
test-query:
	curl -X POST http://localhost:8000/chat \
		-H "Content-Type: application/json" \
		-d '{"message": "What are the latest NVDA earnings?"}'

stream-test:
	curl -X POST http://localhost:8000/chat \
		-H "Content-Type: application/json" \
		-d '{"message": "Latest Tesla news?", "stream": true}'