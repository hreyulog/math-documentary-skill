#!/usr/bin/env node
/** Optional encoded-MP4 playback/seek check. In the current project, install
 * `npm install --no-save playwright`.
 * node browser_check.mjs movie.mp4 --out qa/browser --chrome /path/to/chrome
 * No material leaves this machine: HTTP binds only 127.0.0.1 on an ephemeral port.
 * Screenshots and muted playback are not a full visual, listening or phone review.
 */
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import http from 'node:http';
import {createRequire} from 'node:module';
import {createHash} from 'node:crypto';
const require = createRequire(import.meta.url);

const help = `Usage: node browser_check.mjs VIDEO.mp4 [options]
  --out DIR                 Output directory (default qa/browser)
  --chrome PATH             Chrome/Chromium executable; or CHROME_BINARY
  --playwright-module PATH  Package name or installed module directory; or PLAYWRIGHT_MODULE
  --times 0,1.3,5           Seek seconds; default 5 evenly spaced positions
  --width 390 --height 844  Browser viewport (not a physical phone)
  --fps 30                  Timing tolerance / final frame offset
  --play-seconds 1.2        Short muted playback duration, maximum 5 seconds
  --help                    Show this help
Install Playwright in the current project: npm install --no-save playwright
The package is resolved near this script, then from the current working directory.
If Chrome is not supplied, PATH and standard installed Chrome paths are checked, then
Playwright's bundled Chromium is used if installed. No browser is downloaded.
Report technicalPass describes decoding/playback only; manual review stays false.`;

function parse(args) {
  if (args.includes('--help') || args.includes('-h')) {console.log(help); process.exit(0);}
  const result = {out: 'qa/browser', width: 390, height: 844, fps: 30, 'play-seconds': 1.2};
  const flags = new Set(['out', 'chrome', 'playwright-module', 'times', 'width', 'height', 'fps', 'play-seconds']);
  for (let i = 0; i < args.length; i++) {
    const arg = args[i];
    if (arg.startsWith('--')) {
      const key = arg.slice(2);
      if (!flags.has(key) || args[i + 1] === undefined || args[i + 1].startsWith('--')) throw new Error(`Unknown or incomplete option: ${arg}\n${help}`);
      result[key] = args[++i];
    } else if (!result.video) result.video = arg;
    else throw new Error(`Unexpected argument: ${arg}`);
  }
  if (!result.video) throw new Error(help);
  for (const key of ['width', 'height', 'fps', 'play-seconds']) {
    result[key] = Number(result[key]);
    if (!Number.isFinite(result[key]) || result[key] <= 0) throw new Error(`${key} must be positive`);
  }
  if (result['play-seconds'] > 5) throw new Error('--play-seconds may not exceed 5');
  if (![result.width, result.height].every(Number.isInteger)) throw new Error('Viewport dimensions must be integers');
  return result;
}

function findChrome(explicit) {
  const onPath = name => (process.env.PATH || '').split(path.delimiter).map(folder => path.join(folder, name)).find(candidate => fs.existsSync(candidate) && fs.statSync(candidate).isFile());
  const requested = explicit || process.env.CHROME_BINARY || process.env.BROWSER_EXECUTABLE;
  if (requested) {
    const resolved = fs.existsSync(requested) ? requested : onPath(requested);
    if (!resolved) throw new Error(`Chrome executable does not exist or is not on PATH: ${requested}`);
    return path.resolve(resolved);
  }
  const pathNames = process.platform === 'win32' ? ['chrome.exe', 'chromium.exe'] : ['google-chrome', 'google-chrome-stable', 'chromium', 'chromium-browser'];
  const fromPath = pathNames.map(onPath).find(Boolean);
  if (fromPath) return fromPath;
  const candidates = process.platform === 'win32' ? [
    process.env.PROGRAMFILES && path.join(process.env.PROGRAMFILES, 'Google/Chrome/Application/chrome.exe'),
    process.env['PROGRAMFILES(X86)'] && path.join(process.env['PROGRAMFILES(X86)'], 'Google/Chrome/Application/chrome.exe'),
    process.env.LOCALAPPDATA && path.join(process.env.LOCALAPPDATA, 'Google/Chrome/Application/chrome.exe'),
  ] : process.platform === 'darwin' ? ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', '/Applications/Chromium.app/Contents/MacOS/Chromium'] : ['/usr/bin/google-chrome', '/usr/bin/google-chrome-stable', '/usr/bin/chromium', '/usr/bin/chromium-browser'];
  return candidates.filter(Boolean).find(candidate => fs.existsSync(candidate));
}

let args;
try {args = parse(process.argv.slice(2));} catch (error) {console.error(error.message); process.exit(1);}
const file = path.resolve(args.video);
const out = path.resolve(args.out);
fs.mkdirSync(out, {recursive: true});
const report = {
  technicalPass: false, file, viewport: {width: args.width, height: args.height},
  encodedFileDirectly: true, usesRemotionStudio: false, mutedDuringPlayback: true,
  manualReview: {visualLayoutAndCaptions: false, fullListening: false, physicalPhone: false, platformUpload: false},
  scope: 'Short muted playback and seek screenshots. Review images manually; this does not establish full movie quality.',
  soughtFrames: [],
};
let browser;
let server;
const sockets = new Set();
try {
  if (!fs.existsSync(file) || !fs.statSync(file).isFile() || !fs.statSync(file).size) throw new Error(`Completed MP4 is missing or empty: ${file}`);
  report.bytes = fs.statSync(file).size;
  const hash = createHash('sha256');
  for await (const chunk of fs.createReadStream(file)) hash.update(chunk);
  report.sha256 = hash.digest('hex');
  let chromium;
  const requestedModule = args['playwright-module'] || process.env.PLAYWRIGHT_MODULE;
  try {
    if (requestedModule) ({chromium} = require(requestedModule));
    else {
      try {({chromium} = require('playwright'));}
      catch {({chromium} = createRequire(path.join(process.cwd(), 'package.json'))('playwright'));}
    }
  } catch (error) {throw new Error(`Playwright is unavailable. Run npm install --no-save playwright in the current project, or use --playwright-module. ${error.message}`);}
  server = http.createServer((req, res) => {
    if (!['GET', 'HEAD'].includes(req.method)) {res.writeHead(405); res.end(); return;}
    const url = new URL(req.url, 'http://127.0.0.1');
    if (url.pathname === '/video.mp4') {
      const size = fs.statSync(file).size;
      const range = req.headers.range;
      let start = 0, end = size - 1;
      if (range) {
        const match = /^bytes=(\d*)-(\d*)$/.exec(range);
        if (!match || (!match[1] && !match[2])) {res.writeHead(416, {'Content-Range': `bytes */${size}`}); res.end(); return;}
        if (!match[1]) start = Math.max(0, size - Number(match[2]));
        else {start = Number(match[1]); if (match[2]) end = Math.min(Number(match[2]), end);}
        if (!Number.isSafeInteger(start) || !Number.isSafeInteger(end) || start > end || start >= size) {res.writeHead(416, {'Content-Range': `bytes */${size}`}); res.end(); return;}
      }
      const headers = {'Content-Type': 'video/mp4', 'Accept-Ranges': 'bytes', 'Cache-Control': 'no-store', 'Content-Length': end - start + 1};
      if (range) headers['Content-Range'] = `bytes ${start}-${end}/${size}`;
      res.writeHead(range ? 206 : 200, headers);
      if (req.method === 'HEAD') res.end();
      else {
        const stream = fs.createReadStream(file, {start, end});
        stream.on('error', () => res.destroy());
        res.on('close', () => stream.destroy());
        stream.pipe(res);
      }
      return;
    }
    if (url.pathname !== '/') {res.writeHead(404); res.end(); return;}
    res.writeHead(200, {'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store'});
    res.end(`<!doctype html><html><meta name="viewport" content="width=device-width,initial-scale=1"><body style="margin:0;background:#101B28;overflow:hidden"><video id="video" muted playsinline preload="auto" style="display:block;width:100vw;height:100vh;object-fit:contain" src="/video.mp4"></video><script>window.mediaErrors=[];document.querySelector('video').addEventListener('error',()=>{const e=document.querySelector('video').error;window.mediaErrors.push({code:e?.code,message:e?.message});});</script></body></html>`);
  });
  server.on('connection', socket => {sockets.add(socket); socket.on('close', () => sockets.delete(socket));});
  await new Promise((resolve, reject) => {server.once('error', reject); server.listen(0, '127.0.0.1', resolve);});
  const executablePath = findChrome(args.chrome);
  report.browserExecutable = executablePath || 'Playwright bundled Chromium (must already be installed)';
  browser = await chromium.launch({...(executablePath ? {executablePath} : {}), headless: true});
  report.browserVersion = await browser.version();
  report.host = `${os.platform()} ${os.release()}`;
  const page = await browser.newPage({viewport: report.viewport});
  page.setDefaultTimeout(15000);
  await page.goto(`http://127.0.0.1:${server.address().port}/`);
  await page.waitForFunction(() => document.querySelector('video').readyState >= 2);
  report.loaded = await page.evaluate(() => {
    const video = document.querySelector('video');
    return {width: video.videoWidth, height: video.videoHeight, duration: video.duration, readyState: video.readyState, error: video.error ? {code: video.error.code, message: video.error.message} : null};
  });
  if (!Number.isFinite(report.loaded.duration) || report.loaded.duration <= 0 || report.loaded.error) throw new Error('Video metadata/duration is invalid');
  const playSeconds = Math.min(args['play-seconds'], report.loaded.duration * 0.6);
  report.playback = await page.evaluate(async seconds => {
    const video = document.querySelector('video');
    const start = video.currentTime;
    await video.play();
    await new Promise(resolve => setTimeout(resolve, seconds * 1000));
    video.pause();
    const quality = video.getVideoPlaybackQuality();
    return {elapsedMediaSeconds: video.currentTime - start, decodedFrames: quality.totalVideoFrames, droppedFrames: quality.droppedVideoFrames, error: video.error ? {code: video.error.code, message: video.error.message} : null};
  }, playSeconds);
  if (report.playback.error || report.playback.elapsedMediaSeconds < Math.min(0.3, playSeconds * 0.4) || report.playback.decodedFrames < 1) throw new Error('Muted playback did not advance/decode normally');
  const finalTime = Math.max(0, report.loaded.duration - 1 / args.fps);
  const times = args.times ? args.times.split(',').map(Number) : Array.from({length: 5}, (_, i) => finalTime * i / 4);
  if (!times.length || times.some(time => !Number.isFinite(time) || time < 0 || time >= report.loaded.duration)) throw new Error('Seek times must be finite seconds within the movie');
  for (const [index, time] of times.entries()) {
    const sought = await page.evaluate(async target => {
      const video = document.querySelector('video');
      video.pause();
      if (Math.abs(video.currentTime - target) > 0.000001) {
        await new Promise((resolve, reject) => {
          const done = () => {clearTimeout(timeout); resolve();};
          const timeout = setTimeout(() => {video.removeEventListener('seeked', done); reject(new Error(`Seek timeout at ${target}`));}, 10000);
          video.addEventListener('seeked', done, {once: true});
          video.currentTime = target;
        });
      }
      await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
      return {requestedSeconds: target, actualSeconds: video.currentTime, readyState: video.readyState, error: video.error ? {code: video.error.code, message: video.error.message} : null};
    }, time);
    if (sought.error || sought.readyState < 2 || Math.abs(sought.actualSeconds - time) > 1 / args.fps) throw new Error(`Seek check failed at ${time}`);
    const filename = `browser-${String(index).padStart(2, '0')}-${time.toFixed(4).replace('.', '_')}.png`;
    await page.screenshot({path: path.join(out, filename)});
    report.soughtFrames.push({...sought, screenshot: filename});
  }
  report.mediaErrors = await page.evaluate(() => window.mediaErrors);
  if (report.mediaErrors.length) throw new Error('Browser recorded media errors');
  report.technicalPass = true;
} catch (error) {
  report.error = error.stack || String(error);
  process.exitCode = 1;
} finally {
  if (browser) await browser.close().catch(() => {});
  if (server) {
    for (const socket of sockets) socket.destroy();
    if (server.listening) await new Promise(resolve => server.close(resolve));
  }
  fs.writeFileSync(path.join(out, 'browser-check.json'), JSON.stringify(report, null, 2));
  console.log(JSON.stringify({report: path.join(out, 'browser-check.json'), technicalPass: report.technicalPass, error: report.error || null}));
}
