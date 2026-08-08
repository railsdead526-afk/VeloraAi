# VeloraAi
VeloraAi adalah backend API berbasis FastAPI yang menyediakan fitur autentikasi pengguna dan manajemen item. Project ini menerapkan registrasi, login, JWT authentication, serta operasi CRUD dengan ownership-based access control agar setiap user hanya dapat mengakses item miliknya sendiri. Project juga dilengkapi automated testing menggunakan pytest untuk memastikan setiap fitur berjalan dengan baik.


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
python -m venv venv
source venv/bin/activate
python -m pip install -r requirements.txt
uvicorn app.main:app --reload

## Run Tests
python -m pytest -v

## Project Structure
app/
  api/
  core/
  crud/
  models/
  schemas/
  main.py

tests/
  conftest.py
  test_auth.py
  test_items.py

## Notes
- Database files are ignored using `.gitignore`
- Authentication uses JWT
- Item access is restricted by owner
