#!/usr/bin/env python3
"""mywedflix face-scan robot — InsightFace (ArcFace) edition.

Runs on GitHub Actions. Same HTTP contract as the old Node robot
(scan_jobs.php / album_data.php / face_save.php), but:
  - detection  = SCRFD (buffalo_s)  → finds small / side faces MobileNet missed
  - embedding  = ArcFace 512-dim, L2-normalised → far more accurate matching
Embeddings are packed as little-endian float32, base64. `v=2` in the payload
marks the new model so the server never mixes them with the old 128-dim ones.
"""
import os
import sys
import time
import json
import base64

import numpy as np
import requests
import cv2
from insightface.app import FaceAnalysis

BASE = os.environ.get('MW_BASE', 'https://mywedflix.com').rstrip('/')
TOKEN = os.environ.get('MW_TOKEN', '')
DEADLINE = time.time() + 45 * 60          # stop before the runner's limit
MODEL_V = 2                               # 2 = ArcFace 512-dim (old face-api = 128-dim)
DET_SIZE = (768, 768)                     # bigger = catches smaller faces in group shots
MIN_FACE = 40                             # px, drop faces smaller than this (weak embeddings)
MIN_SCORE = 0.5

if not TOKEN:
    print('MW_TOKEN secret is not set', file=sys.stderr)
    sys.exit(1)


def safe_url(u):
    return str(u).split('?')[0]


def mask(code):
    return str(code)[:4] + '***'


sess = requests.Session()


def jget(url):
    r = sess.get(url, timeout=60)
    if not r.ok:
        raise RuntimeError('GET %s -> %d' % (safe_url(url), r.status_code))
    return r.json()


def jpost(url, fields):
    r = sess.post(url, data=fields, timeout=60)
    if not r.ok:
        raise RuntimeError('POST %s -> %d' % (safe_url(url), r.status_code))
    return r.json()


app = None


def load_models():
    global app
    if app is not None:
        return
    a = FaceAnalysis(name='buffalo_s',
                     allowed_modules=['detection', 'recognition'],
                     providers=['CPUExecutionProvider'])
    a.prepare(ctx_id=-1, det_size=DET_SIZE)
    app = a


def b64emb(emb):
    return base64.b64encode(np.asarray(emb, dtype='<f4').tobytes()).decode('ascii')


def detect(img_bytes):
    arr = np.frombuffer(img_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)   # BGR, what insightface expects
    if img is None:
        return []
    out = []
    for f in app.get(img):
        x1, y1, x2, y2 = f.bbox
        if min(x2 - x1, y2 - y1) < MIN_FACE:
            continue
        if float(getattr(f, 'det_score', 1.0)) < MIN_SCORE:
            continue
        emb = getattr(f, 'normed_embedding', None)
        if emb is None:
            continue
        out.append(b64emb(emb))
    return out


def scan_album(code, tok, alb):
    q = 'code=' + requests.utils.quote(code) + '&t=' + requests.utils.quote(tok)
    if alb.get('mode') == 'full':
        jpost(BASE + '/face_save.php?' + q, {'action': 'reset', 'i': alb['i'], 'h': alb['h']})
    fresh = '&fresh=1' if alb.get('mode') == 'inc' else ''
    j = jget(BASE + '/album_data.php?' + q + '&i=' + str(alb['i']) + fresh)
    photos = (j or {}).get('photos') or []
    skip = set(alb.get('skip') or [])
    targets = [u for u in photos if u not in skip]
    faces = 0
    done = 0
    batch = []

    def flush():
        if not batch:
            return
        items = json.dumps(batch)
        del batch[:]
        jpost(BASE + '/face_save.php?' + q, {'action': 'add', 'i': alb['i'], 'items': items, 'v': MODEL_V})

    for u in targets:
        if time.time() > DEADLINE:
            flush()
            print('  time limit, %d/%d done — next run continues' % (done, len(targets)))
            return {'done': done, 'faces': faces, 'finished': False}
        try:
            r = sess.get(u + '=w1200', timeout=60)
            if not r.ok:
                raise RuntimeError('img %d' % r.status_code)
            ds = detect(r.content)
            batch.append({'url': u, 'd': ds})
            faces += len(ds)
        except Exception:
            batch.append({'url': u, 'd': []})   # checkpoint even on failure
        done += 1
        if len(batch) >= 10:
            flush()
        if done % 50 == 0:
            print('  ... %s: %d/%d - %d faces' % (alb.get('title', ''), done, len(targets), faces))
    flush()
    jpost(BASE + '/face_save.php?' + q, {'action': 'done', 'i': alb['i'], 'h': alb['h']})
    print('  ok %s: %d new photos - %d faces' % (alb.get('title', ''), done, faces))
    return {'done': done, 'faces': faces, 'finished': True}


def process_enrollments():
    """Embed pending client selfies with the SAME ArcFace model as the albums."""
    try:
        jobs = (jget(BASE + '/enroll_jobs.php?t=' + requests.utils.quote(TOKEN)) or {}).get('jobs') or []
    except Exception as e:
        print('enroll: job list failed (%s)' % e)
        return
    if not jobs:
        return
    print('%d selfie enrollment(s) pending' % len(jobs))
    load_models()
    for j in jobs:
        cid = j.get('client_id')
        tok = j.get('t')
        try:
            r = sess.get(j.get('img', ''), timeout=60)
            if not r.ok:
                raise RuntimeError('img %d' % r.status_code)
            arr = np.frombuffer(r.content, dtype=np.uint8)
            im = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            faces = app.get(im) if im is not None else []
            if not faces:
                jpost(BASE + '/face_enroll_save.php', {'c': cid, 't': tok, 'fail': '1'})
                print('  enroll %s: no clear face' % cid)
                continue
            faces.sort(key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]), reverse=True)
            emb = b64emb(faces[0].normed_embedding)   # largest face = the selfie subject
            jpost(BASE + '/face_enroll_save.php', {'c': cid, 't': tok, 'd': emb})
            print('  enroll %s: ok' % cid)
        except Exception as e:
            print('  enroll %s: error (%s)' % (cid, e))


def main():
    process_enrollments()   # selfies first — the user's photos appear fastest
    jobs = (jget(BASE + '/scan_jobs.php?t=' + requests.utils.quote(TOKEN)) or {}).get('jobs') or []
    print('%d premiere(s) with albums' % len(jobs))
    models_ready = False
    tot_p = 0
    tot_f = 0
    for job in jobs:
        if time.time() > DEADLINE:
            break
        q = 'code=' + requests.utils.quote(job['code']) + '&t=' + requests.utils.quote(job['t'])
        try:
            st = jpost(BASE + '/face_save.php?' + q, {'action': 'status'})
        except Exception as e:
            print('x %s: status failed (%s)' % (mask(job['code']), e))
            continue
        need = (st or {}).get('need') or []
        if not need:
            print('- %s: up to date' % (job.get('names') or mask(job['code'])))
            continue
        print('> %s: %d album(s) need scanning' % (job.get('names') or mask(job['code']), len(need)))
        if not models_ready:
            load_models()
            models_ready = True
            print('  models loaded (buffalo_s / ArcFace 512-dim)')
        for alb in need:
            if time.time() > DEADLINE:
                break
            r = scan_album(job['code'], job['t'], alb)
            tot_p += r['done']
            tot_f += r['faces']
    print('Run complete: %d photos scanned, %d faces saved.' % (tot_p, tot_f))


if __name__ == '__main__':
    try:
        main()
        sys.exit(0)
    except Exception as e:
        print('FATAL:', e, file=sys.stderr)
        sys.exit(1)
