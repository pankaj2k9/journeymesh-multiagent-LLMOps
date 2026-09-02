.PHONY: help backend-install backend-run backend-test frontend-install frontend-dev frontend-build frontend-test migrate eval verify

help:
	@echo "JourneyMesh - Every journey, intelligently connected."
	@echo ""
	@echo "  make backend-install   Install backend dependencies"
	@echo "  make backend-run       Run the FastAPI development server"
	@echo "  make backend-test      Run the backend test suite"
	@echo "  make migrate           Apply Alembic migrations"
	@echo "  make eval              Run the offline evaluation suite"
	@echo "  make frontend-install  Install frontend dependencies"
	@echo "  make frontend-dev      Run the Vite development server"
	@echo "  make frontend-build    Produce a production frontend build"
	@echo "  make frontend-test     Run the frontend test suite"
	@echo "  make verify            Run the full verification pipeline"

backend-install:
	cd backend && pip install -r requirements.txt

backend-run:
	cd backend && uvicorn app.main:app --reload --port 8000

backend-test:
	cd backend && pytest -q

migrate:
	cd backend && alembic upgrade head

eval:
	cd backend && python -m evals.run_offline_eval

frontend-install:
	cd frontend && npm install

frontend-dev:
	cd frontend && npm run dev

frontend-build:
	cd frontend && npm run build

frontend-test:
	cd frontend && npm run test -- --run

verify: backend-test frontend-test frontend-build
