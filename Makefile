.PHONY: all dev api web install install-api install-web build lint clean help

# Default target
all: dev

# Start full development suite (API + Web)
dev:
	@echo "Starting full development suite..."
	@$(MAKE) -j2 api web

# Start API server
api:
	uv run api

# Start web frontend
web:
	cd packages/web && npm run dev

# Install all dependencies
install: install-api install-web

install-api:
	uv sync

install-web:
	cd packages/web && npm install

# Build for production
build: build-web

build-web:
	cd packages/web && npm run build

# Lint
lint: lint-web

lint-web:
	cd packages/web && npm run lint

# Clean build artifacts
clean:
	rm -rf packages/web/dist
	rm -rf packages/web/node_modules/.vite
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true

# Help
help:
	@echo "transcripts - YouTube transcription suite"
	@echo ""
	@echo "Usage:"
	@echo "  make dev          Start full suite (API + Web) in parallel"
	@echo "  make api          Start API server only"
	@echo "  make web          Start web frontend only"
	@echo "  make install      Install all dependencies"
	@echo "  make build        Build for production"
	@echo "  make lint         Run linters"
	@echo "  make clean        Remove build artifacts"
	@echo "  make help         Show this help"
