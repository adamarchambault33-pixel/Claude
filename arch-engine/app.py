"""Arch Statement-to-Proposal Engine — local web app.

A thin web wrapper around the same extract + structure pipeline the CLI uses.
Open it in a browser, drop in a statement PDF, and see the clean JSON.

Run:
    uvicorn app:app --reload
    # then open http://127.0.0.1:8000
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from fastapi import FastAPI, File, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from extract import extract_raw
from structure import DEFAULT_MODEL, structure_statement

load_dotenv()

app = FastAPI(title="Arch Statement-to-Proposal Engine")

STATIC_DIR = Path(__file__).parent / "static"
MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB — statements are small


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/api/process")
async def process(statement: UploadFile = File(...)) -> JSONResponse:
    """Run one uploaded PDF through stage 1 (extract) and stage 2 (structure)."""
    filename = statement.filename or "upload.pdf"
    if not filename.lower().endswith(".pdf"):
        return _error("Please upload a PDF file.", status=400)

    data = await statement.read()
    if not data:
        return _error("The uploaded file is empty.", status=400)
    if len(data) > MAX_UPLOAD_BYTES:
        return _error("File is too large (limit 20 MB).", status=400)

    if not os.environ.get("ANTHROPIC_API_KEY"):
        return _error(
            "ANTHROPIC_API_KEY is not set on the server. "
            "Add it to arch-engine/.env and restart.",
            status=500,
        )

    tmp_path: Path | None = None
    try:
        # pdfplumber needs a path, so spool the upload to a temp file.
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(data)
            tmp_path = Path(tmp.name)

        # Stage 1: Extract
        try:
            raw_text = extract_raw(tmp_path)
        except ValueError as exc:
            return _error(str(exc), status=422)

        # Stage 2: Structure
        statement_model = structure_statement(raw_text, model=DEFAULT_MODEL)

        return JSONResponse(
            {
                "ok": True,
                "filename": filename,
                "model": DEFAULT_MODEL,
                "raw_chars": len(raw_text),
                "data": statement_model.model_dump(),
            }
        )
    except anthropic.APIError as exc:
        return _error(f"Anthropic API error: {exc}", status=502)
    except RuntimeError as exc:
        return _error(str(exc), status=502)
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)


def _error(message: str, *, status: int) -> JSONResponse:
    return JSONResponse({"ok": False, "error": message}, status_code=status)
