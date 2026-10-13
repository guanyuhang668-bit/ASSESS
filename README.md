# ASSESS: A structured-feedback tool for rubric-grounded UML diagram assessment

ASSESS is an open-source classroom tool for formative assessment of UML modeling assignments. It imports StarUML project files and converts them into a structured representation of diagram elements, relationship types and endpoints, behavioral events, and containers. This representation — not a diagram screenshot — is evaluated against the rubric defined for the submitted diagram type, and the result is returned as an overall score, indicator-level scores, localized descriptions of detected problems, and revision suggestions.

The same rubric-grounded assessment can be presented in three ways: one-shot complete feedback, multi-round guided feedback, and progressive feedback, which let instructors control how much diagnostic detail is disclosed to students after each submission. In a course deployment with 127 students, the staged modes were associated with higher mean improvement rates than one-shot complete feedback; progressive feedback showed the highest observed mean improvement rate (61.9%) and positive-improvement coverage (100.0%, n = 32). Scenario-dependent modeling judgments can remain ambiguous, so instructor review stays part of the workflow.

## Scope

- **Diagram types:** use-case, class, sequence, and swimlane diagrams.
- **Input:** StarUML project files (`.mdj`); the diagram image is stored alongside each submission for reference.
- **Rubric:** diagram-specific primary indicators, each expanded into fine-grained secondary criteria that state concrete modeling requirements; the same indicator set also aggregates into broader modeling dimensions such as element identification, relationship configuration, and notation expression.
- **Outputs:** total score, indicator-level scores, localized defects, revision suggestions, and ability profiles that help instructors spot recurring difficulties.

## Requirements

- Local development: Python 3.10+ and Node.js.
- Docker Compose stack: Python 3.11, Node.js 20, PostgreSQL 16, Redis 7, and MinIO.
- A DeepSeek-V3-compatible (or other OpenAI-compatible) LLM service. A built-in `mock` client runs the whole pipeline offline, with no API key and no network.

## Quick start

### Docker Compose (full stack)

```bash
git clone https://github.com/guanyuhang668-bit/ASSESS.git
cd ASSESS
cp backend/.env.example backend/.env    # fill in your own LLM API keys
docker compose up --build
```

- Frontend: http://localhost:5173
- Backend health check: http://localhost:8000/health
- MinIO console: http://localhost:9001

Compose starts PostgreSQL, Redis, MinIO, the backend, the ARQ worker, and the frontend. On startup the backend seeds an administrator account and imports the four rubrics from `backend/configs/rubrics/`.

### Offline self-check (no database, Redis, or API key)

Runs the parse → rubric scoring → summary pipeline against the built-in `mock` LLM client:

```bash
cd backend
python scripts/e2e_mock.py <your.mdj> --rubric configs/rubrics/use_case.yaml
```

### Local development without Docker

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env

alembic upgrade head                                  # or set AUTO_CREATE_TABLES=true in .env
python scripts/seed.py --admin-user you --admin-pass '<your-password>'
arq app.workers.grading_worker.WorkerSettings &       # grading worker, keep it running
uvicorn app.main:app --reload                         # http://localhost:8000/health

# Frontend
cd ../frontend
npm install
npm run dev                                           # http://localhost:5173
```

## Repository layout

```
backend/
  app/uml_grader/      StarUML .mdj parser and structured intermediate representation
  app/services/        grading pipeline (rubric loader, CoT runner, repair), LLM clients
  app/api/             auth, admin, submissions, rubrics, grading, teacher, analysis, chat
  app/workers/         ARQ worker and job enqueueing
  configs/rubrics/     rubric definitions for the four diagram types
  configs/prompts/     Jinja2 prompt templates
  alembic/             database migrations
frontend/              Vite + React + TypeScript browser interface
scripts/               multi-model benchmark and analysis utilities
docker-compose.yml     PostgreSQL 16, Redis 7, MinIO, backend, worker, frontend
```

## Documentation

The full technical documentation (directory layout, configuration reference, HTTP API, grading pipeline, deployment notes, and a pre-release security checklist) is available in Chinese in [README.zh-CN.md](README.zh-CN.md).

## License

Released under the MIT License (see [LICENSE](LICENSE)).

## Citation

If you use ASSESS in academic work, please cite: *ASSESS: A structured-feedback tool for rubric-grounded UML diagram assessment*, Binju Huang, Yuhang Guan, Junhao Wang.
