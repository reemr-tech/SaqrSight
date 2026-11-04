"""SaqrSight milestone 1: local submissions and explicitly simulated reports."""
from contextlib import contextmanager
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
import html
import json
import os
import sqlite3
import uuid
import warnings

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from PIL import Image, UnidentifiedImageError

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get('SAQRSIGHT_DATA_DIR', ROOT / 'data')).resolve()
MEDIA = DATA / 'media'
MEDIA.mkdir(parents=True, exist_ok=True)
MAX_BYTES = 10 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = 20_000_000
app = FastAPI(title='SaqrSight', version='0.1.0')
app.mount('/static', StaticFiles(directory=ROOT / 'static'), name='static')

@contextmanager
def db():
    con = sqlite3.connect(DATA / 'saqrsight.sqlite3')
    con.row_factory = sqlite3.Row
    try:
        con.execute('CREATE TABLE IF NOT EXISTS reports (id TEXT PRIMARY KEY, created_at TEXT, payload TEXT NOT NULL, image_name TEXT)')
        yield con
        con.commit()
    finally:
        con.close()

with db():
    pass

def get_record(report_id):
    with db() as con:
        row = con.execute('SELECT * FROM reports WHERE id=?', (report_id,)).fetchone()
    if row is None:
        raise HTTPException(404, 'Report not found.')
    return row

def make_report(caption, language, image_meta, report_id):
    now = datetime.now(timezone.utc).isoformat()
    sections = [
        ('Overall assessment', 'Sample only — no credibility assessment has been performed.'),
        ('Confidence score', 'Not available. No trained model has been connected.'),
        ('Text analysis', 'Sample placeholder — text analysis is not connected.' if caption else 'Not applicable — no text supplied.'),
        ('Media analysis', 'Sample placeholder — synthetic-media detection is not connected.' if image_meta else 'Not applicable — no image supplied.'),
        ('Consistency check', 'Sample placeholder — caption–image model is not connected.' if caption and image_meta else 'Not applicable — both text and an image are required.'),
        ('Issue classification', 'Not assessed.'),
        ('Review priority', 'Not assigned in sample mode.'),
        ('Panic language indicators', 'Not assessed.'),
        ('Previous media appearances', 'Not searched — reverse image search is not connected.'),
        ('Official source evidence', 'Not searched — official-source retrieval is not connected.'),
        ('Recommended action', 'Check relevant official sources and original media context. This sample report cannot establish whether the claim is true or false.'),
    ]
    return dict(id=report_id, created_at=now, mode='sample', caption=caption,
                language=language, image=image_meta,
                notice='WORKFLOW DEMONSTRATION ONLY. All analytical findings are placeholders, not AI results.',
                sections=[dict(title=t, finding=f) for t, f in sections])

@app.get('/', response_class=HTMLResponse)
def home():
    return (ROOT / 'static' / 'index.html').read_text(encoding='utf-8')

@app.get('/api/health')
def health():
    return {'status': 'ok', 'mode': 'sample', 'version': '0.1.0'}

@app.post('/api/reports', status_code=201)
async def create_report(caption: str = Form(''), language: str = Form('auto'), image: UploadFile | None = File(None)):
    caption = caption.strip()
    if len(caption) > 10000:
        raise HTTPException(422, 'Text must be 10,000 characters or fewer.')
    if language not in {'auto', 'ar', 'en'}:
        raise HTTPException(422, 'Choose Arabic, English, or automatic language selection.')
    if not caption and (image is None or not image.filename):
        raise HTTPException(422, 'Enter text or upload an image.')
    rid = str(uuid.uuid4())
    image_meta, stored_name = None, None
    if image is not None and image.filename:
        try:
            raw = await image.read(MAX_BYTES + 1)
        finally:
            await image.close()
        if len(raw) > MAX_BYTES:
            raise HTTPException(413, 'Image must be 10 MB or smaller.')
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('error', Image.DecompressionBombWarning)
                with Image.open(BytesIO(raw)) as im:
                    if im.format not in {'JPEG', 'PNG', 'WEBP'}:
                        raise HTTPException(415, 'Use a JPEG, PNG, or WebP image.')
                    if getattr(im, 'n_frames', 1) != 1:
                        raise HTTPException(415, 'Use a single still image, not an animated file.')
                    im.load()
                    # Re-encode to strip metadata and never retain arbitrary upload bytes.
                    clean = im.convert('RGB')
                    image_meta = {'width': im.width, 'height': im.height, 'original_name': Path(image.filename.replace('\\', '/')).name[:200]}
                    stored_name = rid + '.jpg'
                    clean.save(MEDIA / stored_name, format='JPEG', quality=90)
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
            raise HTTPException(415, 'Invalid image or image exceeds the 20-megapixel safety limit.')
    selected = language
    if language == 'auto':
        selected = ('ar' if any('\u0600' <= c <= '\u06ff' for c in caption) else 'en') if caption else 'not applicable'
    payload = make_report(caption, selected, image_meta, rid)
    try:
        with db() as con:
            con.execute('INSERT INTO reports VALUES (?, ?, ?, ?)', (rid, payload['created_at'], json.dumps(payload, ensure_ascii=False), stored_name))
    except Exception:
        if stored_name:
            (MEDIA / stored_name).unlink(missing_ok=True)
        raise
    return payload

@app.get('/api/reports')
def history():
    with db() as con:
        rows = con.execute('SELECT id,created_at,payload FROM reports ORDER BY created_at DESC LIMIT 100').fetchall()
    return [{'id': r['id'], 'created_at': r['created_at'], 'caption': json.loads(r['payload'])['caption'], 'has_image': bool(json.loads(r['payload'])['image'])} for r in rows]

@app.get('/api/reports/{report_id}')
def read_report(report_id: str):
    return json.loads(get_record(report_id)['payload'])

@app.get('/api/reports/{report_id}/image')
def read_image(report_id: str):
    name = get_record(report_id)['image_name']
    if not name or not (MEDIA / name).is_file():
        raise HTTPException(404, 'Image not found.')
    return FileResponse(MEDIA / name, media_type='image/jpeg', headers={'Cache-Control': 'no-store'})

@app.get('/api/reports/{report_id}/download')
def download(report_id: str, format: str = 'html'):
    p = json.loads(get_record(report_id)['payload'])
    if format == 'json':
        return Response(json.dumps(p, ensure_ascii=False, indent=2), media_type='application/json', headers={'Content-Disposition': f'attachment; filename="SaqrSight-{report_id}.json"'})
    if format != 'html':
        raise HTTPException(422, 'Supported formats: html, json.')
    esc = html.escape
    sections = ''.join(f'<section><h2>{esc(s["title"])}</h2><p>{esc(s["finding"])}</p></section>' for s in p['sections'])
    content = f'''<!doctype html><html lang="en"><meta charset="utf-8"><title>SaqrSight sample report</title><style>body{{font:16px system-ui;max-width:820px;margin:40px auto;padding:20px;color:#173c37}}aside{{padding:18px;background:#fff1d8;border:1px solid #b18432}}section{{break-inside:avoid;border-bottom:1px solid #ddd}}h2{{font-size:18px}}pre{{white-space:pre-wrap;font:inherit}}@media print{{body{{margin:0}}}}</style><h1>SaqrSight · Sample report</h1><aside>{esc(p['notice'])}</aside><p>Report ID: {esc(p['id'])}<br>Created: {esc(p['created_at'])}<br>Language: {esc(p['language'])}</p><h2>Submitted text</h2><pre dir="auto">{esc(p['caption'] or 'No text supplied.')}</pre><p>Image: {esc(p['image']['original_name']) if p['image'] else 'Not supplied'}</p>{sections}<p>Milestone 1 · Local workflow prototype</p></html>'''
    return Response(content, media_type='text/html', headers={'Content-Disposition': f'attachment; filename="SaqrSight-{report_id}.html"'})

@app.delete('/api/reports/{report_id}', status_code=204)
def delete_report(report_id: str):
    row = get_record(report_id)
    with db() as con:
        con.execute('DELETE FROM reports WHERE id=?', (report_id,))
    if row['image_name']:
        (MEDIA / row['image_name']).unlink(missing_ok=True)
    return Response(status_code=204)
