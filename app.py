import asyncio, os, re, json, uuid, zipfile, shutil
from pathlib import Path
from urllib.parse import urlparse
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, HttpUrl
from playwright.async_api import async_playwright
import httpx

BASE = Path(__file__).parent
DOWNLOADS = BASE / 'downloads'
DOWNLOADS.mkdir(exist_ok=True)
app = FastAPI(title='RedNote Bulk Video Downloader')
app.mount('/static', StaticFiles(directory=BASE/'static'), name='static')

jobs = {}

class ScanRequest(BaseModel):
    profile_url: HttpUrl
    max_posts: int = 100
    cookie: str | None = None

class DownloadRequest(BaseModel):
    job_id: str
    indexes: list[int] | None = None


def valid_profile(url: str):
    host = urlparse(url).netloc.lower()
    return 'xiaohongshu.com' in host or 'rednote.com' in host or 'xhslink.com' in host or 'xhslink.cn' in host

async def collect_profile(url, max_posts=100, cookie=None):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        if cookie:
            # Cookie string is supplied by the user; it is not logged or persisted.
            cookies=[]
            for part in cookie.split(';'):
                if '=' in part:
                    k,v=part.strip().split('=',1)
                    cookies.append({'name':k,'value':v,'domain':'.xiaohongshu.com','path':'/'})
            if cookies:
                await context.add_cookies(cookies)
        page = await context.new_page()
        notes = {}

        async def response_handler(resp):
            if 'user_posted' not in resp.url or resp.status != 200:
                return
            try:
                data = await resp.json()
                arr = data.get('data', {}).get('notes', [])
                for n in arr:
                    nid = n.get('note_id') or n.get('id')
                    if not nid: continue
                    notes[nid] = {
                        'id': nid,
                        'title': n.get('display_title') or n.get('title') or '',
                        'type': n.get('type') or n.get('note_type') or '',
                        'url': f'https://www.xiaohongshu.com/explore/{nid}',
                        'cover': (n.get('image_list') or [{}])[0].get('url_default') if n.get('image_list') else None,
                    }
            except Exception:
                pass

        page.on('response', response_handler)
        await page.goto(str(url), wait_until='domcontentloaded', timeout=60000)
        await page.wait_for_timeout(2500)
        stable = 0
        last = 0
        for _ in range(40):
            await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
            await page.wait_for_timeout(1300)
            count = len(notes)
            if count >= max_posts: break
            if count == last:
                stable += 1
            else:
                stable = 0
            last = count
            if stable >= 5: break
        await browser.close()
        return list(notes.values())[:max_posts]

async def resolve_video(note_url, cookie=None):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        if cookie:
            cookies=[]
            for part in cookie.split(';'):
                if '=' in part:
                    k,v=part.strip().split('=',1)
                    cookies.append({'name':k,'value':v,'domain':'.xiaohongshu.com','path':'/'})
            if cookies: await context.add_cookies(cookies)
        page = await context.new_page()
        media=[]
        async def response_handler(resp):
            ct=(resp.headers.get('content-type') or '').lower()
            u=resp.url
            if ('video' in ct or re.search(r'\.(mp4|m3u8)(\?|$)',u,re.I)) and ('xiaohongshu' in u or 'xhscdn' in u or 'sns' in u):
                if u not in media: media.append(u)
        page.on('response', response_handler)
        try:
            await page.goto(note_url, wait_until='domcontentloaded', timeout=60000)
            await page.wait_for_timeout(4000)
            # Some pages expose a video element with a CDN src after hydration.
            srcs = await page.locator('video').evaluate_all("els => els.map(e => e.currentSrc || e.src).filter(Boolean)")
            for s in srcs:
                if s not in media: media.append(s)
        except Exception:
            pass
        await browser.close()
        return media[0] if media else None

@app.get('/health')
async def health():
    return {'status': 'ok'}

@app.get('/', response_class=HTMLResponse)
async def home():
    return (BASE/'templates/index.html').read_text(encoding='utf-8')

@app.post('/api/scan')
async def scan(req: ScanRequest):
    if not valid_profile(str(req.profile_url)):
        raise HTTPException(400, 'URL không phải link RedNote/Xiaohongshu hợp lệ.')
    posts = await collect_profile(str(req.profile_url), min(max(req.max_posts,1),500), req.cookie)
    job_id = uuid.uuid4().hex
    jobs[job_id] = {'posts': posts, 'cookie': req.cookie, 'videos': []}
    # Resolve video media serially to keep load reasonable.
    for i,p in enumerate(posts):
        if str(p.get('type')).lower() in ('video','video_note'):
            p['media_url'] = await resolve_video(p['url'], req.cookie)
        else:
            p['media_url'] = None
        if p.get('media_url'):
            jobs[job_id]['videos'].append(i)
    return {'job_id':job_id, 'posts':posts, 'video_count':len(jobs[job_id]['videos'])}

@app.post('/api/download')
async def download(req: DownloadRequest):
    job=jobs.get(req.job_id)
    if not job: raise HTTPException(404,'Job không tồn tại hoặc đã hết phiên.')
    indexes=req.indexes if req.indexes is not None else job['videos']
    out=DOWNLOADS/req.job_id
    out.mkdir(exist_ok=True)
    files=[]
    async with httpx.AsyncClient(follow_redirects=True, timeout=120) as client:
        for n,idx in enumerate(indexes,1):
            if idx not in job['videos']: continue
            p=job['posts'][idx]
            u=p.get('media_url')
            if not u: continue
            safe=re.sub(r'[^\w\-. ]+','_', p.get('title') or f'video_{idx+1}')[:80].strip() or f'video_{idx+1}'
            path=out/f'{n:03d}_{safe}.mp4'
            try:
                r=await client.get(u, headers={'Referer':'https://www.xiaohongshu.com/'})
                r.raise_for_status()
                path.write_bytes(r.content)
                files.append(path)
            except Exception:
                continue
    if not files: raise HTTPException(502,'Không tải được video nào. Có thể URL CDN đã hết hạn; hãy scan lại.')
    zip_path=DOWNLOADS/f'{req.job_id}.zip'
    with zipfile.ZipFile(zip_path,'w',zipfile.ZIP_DEFLATED) as z:
        for f in files: z.write(f,f.name)
    return FileResponse(zip_path, filename='rednote_videos.zip', media_type='application/zip')
