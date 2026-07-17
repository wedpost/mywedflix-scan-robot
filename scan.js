/* mywedflix face-scan robot — runs on GitHub Actions every 30 minutes.
   Asks the site which albums have unscanned photos, scans ONLY those
   (same models, same 128-number signatures as the in-browser scanner),
   and saves the results back. Checkpoints on the server mean a run that
   hits the time limit simply continues on the next schedule. */
'use strict';

const fs = require('fs');
const path = require('path');
const tf = require('@tensorflow/tfjs-node');
const faceapi = require('@vladmandic/face-api');

const BASE = (process.env.MW_BASE || 'https://mywedflix.com').replace(/\/$/, '');
const TOKEN = process.env.MW_TOKEN || '';
const DEADLINE = Date.now() + 45 * 60 * 1000;   // stop before the runner's limit
const MODEL_DIR = path.join(__dirname, 'models');
const MODEL_FILES = [
  'ssd_mobilenetv1_model-weights_manifest.json',
  'ssd_mobilenetv1_model-shard1',
  'ssd_mobilenetv1_model-shard2',
  'face_landmark_68_model-weights_manifest.json',
  'face_landmark_68_model-shard1',
  'face_recognition_model-weights_manifest.json',
  'face_recognition_model-shard1',
  'face_recognition_model-shard2',
];

if (!TOKEN) { console.error('MW_TOKEN secret is not set'); process.exit(1); }

// public repos show run logs to everyone — so errors never include query
// strings (tokens live there) and premiere codes are always masked
function safeUrl(u) { return String(u).split('?')[0]; }
function mask(code) { return String(code).slice(0, 4) + '***'; }

async function jget(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error('GET ' + safeUrl(url) + ' -> ' + r.status);
  return r.json();
}
async function jpost(url, fields) {
  const body = new URLSearchParams(fields);
  const r = await fetch(url, { method: 'POST', body });
  if (!r.ok) throw new Error('POST ' + safeUrl(url) + ' -> ' + r.status);
  return r.json();
}

async function ensureModels() {
  fs.mkdirSync(MODEL_DIR, { recursive: true });
  for (const f of MODEL_FILES) {
    const p = path.join(MODEL_DIR, f);
    if (fs.existsSync(p) && fs.statSync(p).size > 0) continue;
    const r = await fetch(BASE + '/assets/faceapi/models/' + f);
    if (!r.ok) throw new Error('model download failed: ' + f);
    fs.writeFileSync(p, Buffer.from(await r.arrayBuffer()));
  }
  await faceapi.nets.ssdMobilenetv1.loadFromDisk(MODEL_DIR);
  await faceapi.nets.faceLandmark68Net.loadFromDisk(MODEL_DIR);
  await faceapi.nets.faceRecognitionNet.loadFromDisk(MODEL_DIR);
}

const OPTS = () => new faceapi.SsdMobilenetv1Options({ minConfidence: 0.5 });

function b64(desc) {
  return Buffer.from(new Uint8Array(desc.buffer, desc.byteOffset, desc.byteLength)).toString('base64');
}

async function detect(imgBuf) {
  const t = tf.node.decodeImage(imgBuf, 3);
  try {
    const dets = await faceapi.detectAllFaces(t, OPTS()).withFaceLandmarks().withFaceDescriptors();
    // same quality rule as the browser scanner: tiny/blurry faces cause
    // wrong-person matches, so they are dropped
    return (dets || []).filter(d => {
      const bx = d.detection.box;
      return Math.min(bx.width, bx.height) >= 45 && d.detection.score >= 0.5;
    }).map(d => b64(d.descriptor));
  } finally {
    t.dispose();
  }
}

async function scanAlbum(code, tok, alb) {
  const q = 'code=' + encodeURIComponent(code) + '&t=' + encodeURIComponent(tok);
  if (alb.mode === 'full') {
    await jpost(BASE + '/face_save.php?' + q, { action: 'reset', i: alb.i, h: alb.h });
  }
  const fresh = alb.mode === 'inc' ? '&fresh=1' : '';
  const j = await jget(BASE + '/album_data.php?' + q + '&i=' + alb.i + fresh);
  const photos = (j && j.photos) || [];
  const skip = new Set(alb.skip || []);
  const targets = photos.filter(u => !skip.has(u));
  let faces = 0, done = 0, batch = [];

  async function flush() {
    if (!batch.length) return;
    const items = JSON.stringify(batch); batch = [];
    await jpost(BASE + '/face_save.php?' + q, { action: 'add', i: alb.i, items });
  }

  for (const u of targets) {
    if (Date.now() > DEADLINE) {           // out of time — checkpoint and stop
      await flush();
      console.log(`  ⏸  ${alb.title}: time limit, ${done}/${targets.length} done — next run continues`);
      return { done, faces, finished: false };
    }
    try {
      const r = await fetch(u + '=w1200');          // straight from Google — no proxy
      if (!r.ok) throw new Error('img ' + r.status);
      const ds = await detect(Buffer.from(await r.arrayBuffer()));
      batch.push({ url: u, d: ds });
      faces += ds.length;
    } catch (e) {
      batch.push({ url: u, d: [] });                // checkpoint even on failure
    }
    done++;
    if (batch.length >= 10) await flush();
    if (done % 50 === 0) console.log(`  … ${alb.title}: ${done}/${targets.length} · ${faces} faces`);
  }
  await flush();
  await jpost(BASE + '/face_save.php?' + q, { action: 'done', i: alb.i, h: alb.h });
  console.log(`  ✓ ${alb.title}: ${done} new photos · ${faces} faces`);
  return { done, faces, finished: true };
}

(async () => {
  const { jobs } = await jget(BASE + '/scan_jobs.php?t=' + encodeURIComponent(TOKEN));
  console.log(`${jobs.length} premiere(s) with albums`);
  let modelsReady = false, totP = 0, totF = 0;

  for (const job of jobs) {
    if (Date.now() > DEADLINE) break;
    const q = 'code=' + encodeURIComponent(job.code) + '&t=' + encodeURIComponent(job.t);
    let st;
    try {
      st = await jpost(BASE + '/face_save.php?' + q, { action: 'status' });
    } catch (e) { console.log(`✗ ${mask(job.code)}: status failed (${e.message})`); continue; }
    const need = (st && st.need) || [];
    if (!need.length) { console.log(`· ${job.names || mask(job.code)}: up to date`); continue; }

    console.log(`▶ ${job.names || mask(job.code)}: ${need.length} album(s) need scanning`);
    if (!modelsReady) { await ensureModels(); modelsReady = true; console.log('  models loaded'); }
    for (const alb of need) {
      if (Date.now() > DEADLINE) break;
      const r = await scanAlbum(job.code, job.t, alb);
      totP += r.done; totF += r.faces;
    }
  }
  console.log(`Run complete: ${totP} photos scanned, ${totF} faces saved.`);
  process.exit(0);
})().catch(e => { console.error('FATAL:', e); process.exit(1); });
