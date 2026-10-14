from contextlib import asynccontextmanager
from datetime import date
import sqlite3

from fastapi import FastAPI, HTTPException, Query, Response, status
from .database import get_connection, init_db
from .schemas import StudentCreate, StudentUpdate, StudentResponse

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(
    title="Students Database CRUD API",
    description="Student record management using FastAPI and SQLite. Ollama/AI is intentionally not included.",
    version="1.0.0",
    lifespan=lifespan,
)

def row_to_student(row: sqlite3.Row) -> dict:
    return dict(row)

@app.post("/students", response_model=StudentResponse, status_code=status.HTTP_201_CREATED, tags=["Students"])
def create_student(student: StudentCreate):
    values = student.model_dump(mode="json")
    columns = ", ".join(values.keys())
    placeholders = ", ".join("?" for _ in values)
    with get_connection() as conn:
        cursor = conn.execute(
            f"INSERT INTO students ({columns}) VALUES ({placeholders})",
            tuple(values.values()),
        )
        row = conn.execute("SELECT * FROM students WHERE student_id = ?", (cursor.lastrowid,)).fetchone()
    return row_to_student(row)

@app.get("/students", response_model=list[StudentResponse], tags=["Students"])
def list_students(
    name: str | None = Query(default=None, description="Case-insensitive partial name match"),
    course: str | None = Query(default=None, description="Filter by course"),
    born_after: date | None = Query(default=None, description="Only students born after this date"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    clauses, params = [], []
    if name:
        clauses.append("name LIKE ? COLLATE NOCASE")
        params.append(f"%{name}%")
    if course:
        clauses.append("course = ? COLLATE NOCASE")
        params.append(course)
    if born_after:
        clauses.append("date_of_birth > ?")
        params.append(born_after.isoformat())
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with get_connection() as conn:
        rows = conn.execute(
            f"SELECT * FROM students {where} ORDER BY student_id LIMIT ? OFFSET ?",
            (*params, limit, offset),
        ).fetchall()
    return [row_to_student(row) for row in rows]

@app.get("/students/{student_id}", response_model=StudentResponse, tags=["Students"])
def get_student(student_id: int):
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM students WHERE student_id = ?", (student_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Student not found")
    return row_to_student(row)

@app.put("/students/{student_id}", response_model=StudentResponse, tags=["Students"])
def replace_student(student_id: int, student: StudentCreate):
    values = student.model_dump(mode="json")
    assignments = ", ".join(f"{column} = ?" for column in values)
    with get_connection() as conn:
        cursor = conn.execute(
            f"UPDATE students SET {assignments} WHERE student_id = ?",
            (*values.values(), student_id),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Student not found")
        row = conn.execute("SELECT * FROM students WHERE student_id = ?", (student_id,)).fetchone()
    return row_to_student(row)

@app.patch("/students/{student_id}", response_model=StudentResponse, tags=["Students"])
def update_student(student_id: int, student: StudentUpdate):
    changes = student.model_dump(exclude_unset=True, mode="json")
    with get_connection() as conn:
        existing = conn.execute("SELECT * FROM students WHERE student_id = ?", (student_id,)).fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail="Student not found")
        merged = dict(existing)
        merged.update(changes)
        if not merged.get("email") and not merged.get("phone"):
            raise HTTPException(status_code=422, detail="At least one contact method (email or phone) must remain.")
        if not merged.get("name") or not merged.get("date_of_birth"):
            raise HTTPException(status_code=422, detail="Name and date_of_birth are required.")
        assignments = ", ".join(f"{column} = ?" for column in changes)
        if changes:
            conn.execute(
                f"UPDATE students SET {assignments} WHERE student_id = ?",
                (*changes.values(), student_id),
            )
        row = conn.execute("SELECT * FROM students WHERE student_id = ?", (student_id,)).fetchone()
    return row_to_student(row)

@app.delete("/students/{student_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Students"])
def delete_student(student_id: int):
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM students WHERE student_id = ?", (student_id,))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Student not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@app.get("/health", tags=["Health"])
def health_check():
    return {"status": "ok"}
