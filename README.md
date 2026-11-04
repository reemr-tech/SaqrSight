# SaqrSight — Milestone 1

A functional local submission-and-report application. **Analytical results are sample placeholders.** No AI models, reverse image search, official-source retrieval, video processing, or social-link retrieval are connected yet.

## Run on Windows

Install Python 3.11 or newer, extract the ZIP, and open a terminal in the extracted `saqrsight_step1` folder:

```powershell
py -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m uvicorn app:app --host 127.0.0.1 --port 8000
```

Open **http://127.0.0.1:8000** in your browser. Stop with Ctrl+C.

## Run on macOS / Linux

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m uvicorn app:app --host 127.0.0.1 --port 8000
```

Initial installation requires internet access. Afterwards this milestone runs locally without external service calls or API keys.

## What works

- Arabic or English text (up to 10,000 characters), a still image, or both.
- Manual language selection or a simple Arabic-character heuristic. This heuristic is not a language-identification model and does not analyze credibility.
- Image upload and drag-and-drop, preview, remove, and clear.
- Server-side image decoding, format/size/pixel validation, JPEG re-encoding with metadata removal.
- JPEG, PNG and WebP still images, up to 10 MB and 20 megapixels.
- SQLite submission/report persistence across restarts.
- Saved-report list (most recent 100), opening reports, image retrieval, and deletion of report plus image.
- Eleven report sections explicitly marked as placeholders, unavailable, or not applicable.
- Standalone printable HTML report and structured JSON download; Arabic preserved and HTML escaped.
- Responsive custom browser interface served by FastAPI (used instead of Streamlit for this implementation).

## Quick demonstration

1. Enter a caption or use **Try an example caption**.
2. Upload a supported image if desired.
3. Click **Generate sample assessment**.
4. Inspect submitted content and sample report sections.
5. Download HTML or JSON. Open the HTML in a browser; use Print → Save as PDF if needed.
6. Open **Saved reports**, reopen a report, then delete it if no longer needed.
7. Restart the app to verify undeleted reports remain available.

## Storage and privacy

`data/saqrsight.sqlite3` stores captions and reports; `data/media/` stores re-encoded images. Files stay on the machine running the server; opening a remote server would store them there, not on the browser device. Set `SAQRSIGHT_DATA_DIR` to change the directory. Deletion removes the active database row and associated image; it is not forensic secure erasure of disk blocks or backups. No uploaded files or runtime database are included in this package.

This is a single-user local prototype with no authentication or TLS. Keep the loopback host setting above. Do not expose it to the public internet or use it as a multi-user deployment; that requires authentication, access controls, HTTPS, and request-rate/body limits. SQLite and image processing are suitable for a small local prototype, not a production capacity claim.

## Tests

```bash
python -m pytest -q
```

Tests use isolated temporary storage, not your reports. They cover English/Arabic submissions, images, invalid input, format spoofing, oversized/pixel-limit images, report persistence, HTML escaping, downloads, and deletion.

## Structure

- `app.py`: FastAPI routes, SQLite storage, image validation, report construction.
- `static/`: browser interface and interactions.
- `tests/`: workflow regression tests.
- `requirements.txt`: application and test dependencies.
- `requirements-tested.txt`: exact versions used for the verification run.

## Next milestone integration

Replace `make_report()` placeholders with validated module outputs, retaining the structured `sections` response. Each module should report its status (`completed`, `unavailable`, or `not_applicable`) and supporting findings. Add models one at a time and preserve explicit uncertainty. Do not convert unrelated model scores into a probability that news is false.

No model accuracy or 100% reliability is claimed. The first milestone is the real submission, persistence, and report workflow.

## Falcon interface update — existing Mac installation

1. Stop the server with Control+C in Terminal.
2. Extract the updated ZIP in a different folder.
3. Copy its `static` folder into your existing `saqrsight_step1` folder and choose Replace.
4. Keep your existing `data` folder; it contains your saved reports.
5. Restart with `.venv/bin/python -m uvicorn app:app --host 127.0.0.1 --port 8000`.
6. Open http://127.0.0.1:8000 and press Command+Shift+R to refresh assets.

The falcon identity is drawn as local SVG assets; it needs no image downloads or external fonts. The backend and report sample mode are unchanged.
