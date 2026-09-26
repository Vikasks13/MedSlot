# MedSlot — Diagnostic Test Booking & Payment Service

[![GitHub Repository](https://img.shields.io/badge/GitHub-MedSlot-blue?logo=github)](https://github.com/Vikasks13/MedSlot)
[![Python](https://img.shields.io/badge/Python-3.12-blue?logo=python)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-teal?logo=fastapi)](https://fastapi.tiangolo.com)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-blue?logo=postgresql)](https://www.postgresql.org)
[![Docker](https://img.shields.io/badge/Docker-compose-blue?logo=docker)](https://www.docker.com)

A robust, production-grade backend service built for **EVE Healthcare** to manage diagnostic centres, test bookings, and simulated payments with idempotent webhook handling.

---

## 🚀 Repository & Project Details

- **GitHub Repository**: [https://github.com/Vikasks13/MedSlot](https://github.com/Vikasks13/MedSlot)
- **Framework**: FastAPI (Async Python 3.12)
- **Database**: PostgreSQL 16 (production/Docker) & SQLite with `aiosqlite` (local fallback)
- **ORM / Migrations**: SQLAlchemy 2.0 (Async) + Alembic
- **Authentication**: JWT (JSON Web Tokens) with `HS256` & `passlib[bcrypt]`
- **Testing**: `pytest`, `pytest-asyncio`, `httpx`

---

## 📁 Project Architecture & Structure

```
eve_healthcare/
├── app/
│   ├── main.py                  # FastAPI application entrypoint & lifespan
│   ├── config.py                # Environment configuration (pydantic-settings)
│   ├── database.py              # Async SQLAlchemy engine, session maker, get_db dependency
│   ├── dependencies.py          # Auth & user dependencies (Phase 1)
│   ├── models/                  # SQLAlchemy ORM models
│   │   └── __init__.py
│   ├── schemas/                 # Pydantic validation & serialization schemas
│   │   └── __init__.py
│   ├── routers/                 # API endpoint routers
│   │   └── __init__.py
│   ├── services/                # Business logic services
│   │   └── __init__.py
│   └── utils/                   # Utilities, security helpers, idempotency guards
│       └── __init__.py
├── alembic/                     # Database migrations
│   ├── env.py                   # Async Alembic runner
│   ├── script.py.mako           # Migration template
│   └── versions/                # Generated revision files
├── tests/                       # Unit & integration test suite
│   ├── conftest.py              # Fixtures (in-memory async DB, AsyncClient)
│   └── test_health.py           # Health check & system tests
├── .env.example                 # Template environment variables
├── .env                         # Local environment configuration
├── .gitignore                   # Git ignore rules
├── Dockerfile                   # Production container definition
├── docker-compose.yml           # Multi-container orchestration (API + Postgres + Redis)
├── pytest.ini                   # Pytest configuration
├── requirements.txt             # Dependency manifest
└── README.md                    # Project documentation
```

---

## 🛠️ Quick Start & Local Setup

### Option 1: Running with Docker Compose (Recommended)

To run the entire stack including PostgreSQL and Redis:

```bash
# 1. Clone repository
git clone https://github.com/Vikasks13/MedSlot.git
cd MedSlot

# 2. Build and start services
docker-compose up --build -d

# 3. View live logs
docker-compose logs -f api
```

The service will be live at:
- **API Base**: `http://localhost:8000`
- **Interactive Swagger Docs**: `http://localhost:8000/docs`
- **ReDoc Documentation**: `http://localhost:8000/redoc`
- **Health Check**: `http://localhost:8000/health`

---

### Option 2: Running Locally with Python Virtual Environment

```bash
# 1. Create and activate a Python 3.12 virtual environment
python -m venv .venv

# On Windows (PowerShell):
.venv\Scripts\Activate.ps1
# On macOS/Linux:
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Copy environment configuration
cp .env.example .env

# 4. Start the development server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

---

## 🧪 Running Tests

MedSlot uses `pytest` and `httpx.AsyncClient` with an isolated in-memory SQLite database for high-speed, repeatable tests:

```bash
# Run all tests
pytest

# Run tests with verbose output
pytest -v
```

---

## 🔐 API Reference — Authentication (Phase 1)

| Method | Endpoint | Auth Required | Description |
|:---|:---|:---|:---|
| `POST` | `/api/v1/auth/signup` | No | Register new user with name, unique email, and password |
| `POST` | `/api/v1/auth/login` | No | JSON login returning JWT Bearer access token |
| `POST` | `/api/v1/auth/login/token` | No | Form-encoded login for Swagger UI Authorize modal |
| `GET` | `/api/v1/auth/me` | Bearer Token | Retrieve currently authenticated user profile |

### Example Signup Request
```bash
curl -X POST http://localhost:8000/api/v1/auth/signup \
  -H "Content-Type: application/json" \
  -d '{"name": "Alice Johnson", "email": "alice@example.com", "password": "securepassword123"}'
```

### Example Login Request
```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "alice@example.com", "password": "securepassword123"}'
```

---

## 🏥 API Reference — Diagnostic Centres & Tests (Phase 2)

| Method | Endpoint | Auth Required | Description |
|:---|:---|:---|:---|
| `GET` | `/api/v1/centres` | No | List paginated centres with tests, with optional `location` & `search` filters |
| `POST` | `/api/v1/centres` | Bearer Token | Create a new diagnostic centre |
| `GET` | `/api/v1/centres/{id}` | No | Get centre details by ID including all offered tests |
| `GET` | `/api/v1/centres/{id}/tests` | No | List tests offered by a specific diagnostic centre |
| `POST` | `/api/v1/centres/{id}/tests` | Bearer Token | Add a diagnostic test with name, description, and price to a centre |
| `GET` | `/api/v1/tests/{test_id}` | No | Get specific diagnostic test details |

### Example Create Diagnostic Centre Request
```bash
curl -X POST http://localhost:8000/api/v1/centres \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"name": "Apollo Diagnostics", "location": "Koramangala, Bangalore", "contact_number": "+91-9876543210"}'
```

### Example Add Test to Centre Request
```bash
curl -X POST http://localhost:8000/api/v1/centres/1/tests \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"name": "Complete Blood Count (CBC)", "description": "Full blood panel", "price": 450.00}'
```

---

## 📌 Implementation Phases & Status

- [x] **Phase 0 — Project Bootstrap**: Structure, FastAPI setup, config, Docker, Alembic, health check, pytest suite.
- [x] **Phase 1 — Authentication**: User signup, login, password hashing, JWT creation & verification, OAuth2 Swagger support.
- [x] **Phase 2 — Diagnostic Centres & Tests**: Centre & test management, nested retrieval, pagination, caching.
- [ ] **Phase 3 — Booking System**: Test bookings, ownership validation, status FSM. *(Awaiting approval)*
- [ ] **Phase 4 — Payments & Idempotent Webhook**: Simulated payment provider and webhook idempotency.
- [ ] **Phase 5 — Edge Cases & Hardening**: Ownership checks, error handling, rate limiting.
- [ ] **Phase 6 — Comprehensive Test Suite**: Unit, integration, and duplicate event idempotency tests.
- [ ] **Phase 7 — Final Documentation & Polish**: Complete OpenAPI specs and submission readiness.
