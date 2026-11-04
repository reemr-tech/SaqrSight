import importlib
from io import BytesIO
import sys
from pathlib import Path
import pytest
from PIL import Image
from fastapi.testclient import TestClient

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv('SAQRSIGHT_DATA_DIR', str(tmp_path))
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import app
    importlib.reload(app)
    with TestClient(app.app) as c:
        yield c

def png():
    buf = BytesIO()
    Image.new('RGB', (50, 30), 'green').save(buf, 'PNG')
    return buf.getvalue()

def test_page_and_assets(client):
    assert client.get('/').status_code == 200
    assert 'SaqrSight' in client.get('/').text
    assert client.get('/static/app.js').status_code == 200
    assert client.get('/static/style.css').status_code == 200
    assert client.get('/api/health').json()['mode'] == 'sample'

@pytest.mark.parametrize('caption,lang', [('A claim about Dubai', 'en'), ('خبر عن دبي اليوم', 'ar')])
def test_text_and_language(client, caption, lang):
    r = client.post('/api/reports', data={'caption': caption})
    assert r.status_code == 201
    p = r.json()
    assert p['caption'] == caption and p['language'] == lang
    assert p['mode'] == 'sample' and len(p['sections']) == 11
    assert 'Not applicable' in p['sections'][4]['finding']
    assert client.get('/api/reports/' + p['id']).json() == p
    assert client.get('/api/reports').json()[0]['id'] == p['id']

def test_combined_image_and_text(client):
    r = client.post('/api/reports', data={'caption': 'دبي'}, files={'image': ('../../photo.png', png(), 'image/png')})
    assert r.status_code == 201
    p = r.json()
    assert p['image']['width'] == 50 and p['image']['original_name'] == 'photo.png'
    assert 'Sample placeholder' in p['sections'][4]['finding']
    image = client.get('/api/reports/' + p['id'] + '/image')
    assert image.headers['content-type'] == 'image/jpeg'
    assert Image.open(BytesIO(image.content)).size == (50, 30)

def test_image_only(client):
    p = client.post('/api/reports', files={'image': ('x.png', png(), 'image/png')}).json()
    assert p['language'] == 'not applicable'
    assert 'Not applicable' in p['sections'][2]['finding']

@pytest.mark.parametrize('data', [{}, {'caption': '  '}, {'caption': 'x'*10001}, {'caption': 'x', 'language': 'xx'}])
def test_bad_forms(client, data):
    assert client.post('/api/reports', data=data).status_code == 422
    assert client.get('/api/reports').json() == []

def test_spoofed_and_oversized_upload(client):
    assert client.post('/api/reports', files={'image': ('fake.png', b'<script>x</script>', 'image/png')}).status_code == 415
    assert client.post('/api/reports', files={'image': ('big.png', b'x'*(10*1024*1024+1), 'image/png')}).status_code == 413
    assert client.get('/api/reports').json() == []

def test_unsupported_and_pixel_limit(client):
    buf=BytesIO();Image.new('RGB',(20,20)).save(buf,'GIF')
    assert client.post('/api/reports',files={'image':('x.gif',buf.getvalue(),'image/gif')}).status_code==415
    buf=BytesIO();Image.new('L',(5000,4001)).save(buf,'PNG')
    assert client.post('/api/reports',files={'image':('huge.png',buf.getvalue(),'image/png')}).status_code==415

def test_download_safe_arabic_and_delete(client):
    caption='<script>alert(1)</script> دبي'
    p=client.post('/api/reports', data={'caption':caption}, files={'image':('x.png',png(),'image/png')}).json()
    url='/api/reports/'+p['id']
    exported=client.get(url+'/download?format=html')
    assert '<script>alert(1)</script>' not in exported.text
    assert '&lt;script&gt;' in exported.text and 'دبي' in exported.text
    assert 'WORKFLOW DEMONSTRATION ONLY' in exported.text
    assert 'attachment' in exported.headers['content-disposition']
    assert client.get(url+'/download?format=json').json()==p
    assert client.get(url+'/download?format=exe').status_code==422
    assert client.delete(url).status_code==204
    assert client.get(url).status_code==404
    assert client.get(url+'/image').status_code==404
    assert client.get('/api/reports').json()==[]
    import app
    assert not list(app.MEDIA.iterdir())

def test_persistence(client):
    p=client.post('/api/reports',data={'caption':'Persistent report'}).json()
    import app
    importlib.reload(app)
    with TestClient(app.app) as second:
        assert second.get('/api/reports/'+p['id']).json()['caption']=='Persistent report'

def test_missing_report(client):
    assert client.get('/api/reports/missing').status_code==404
    assert client.delete('/api/reports/missing').status_code==404
