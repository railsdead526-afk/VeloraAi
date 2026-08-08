# VeloraAi

Backend API built with FastAPI.

## Features
- User registration
- User login
- JWT authentication
- Create, list, get, update, delete items
- Ownership-based access control
- Automated tests with pytest

## Tech Stack
- FastAPI
- SQLAlchemy
- SQLite
- Pydantic
- Pytest

## Setup
```bash
python -m venv venv
source venv/bin/activate
python -m pip install -r requirements.txt
uvicorn app.main:app --reload
```
