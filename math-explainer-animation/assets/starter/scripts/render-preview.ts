import path from 'node:path';
import {createHash} from 'node:crypto';
import {existsSync, mkdirSync, readFileSync, writeFileSync} from 'node:fs';
import {bundle} from '@remotion/bundler';
import {getVideoMetadata, openBrowser, renderMedia, renderStill, selectComposition} from '@remotion/renderer';
import config from '../src/config/series.json';

const stillsOnly = process.argv.includes('--stills-only');
const output = path.resolve('output/preview');
mkdirSync(path.join(output, 'keyframes'), {recursive:true});
mkdirSync('qa', {recursive:true});
const hash = (file: string) => createHash('sha256').update(readFileSync(file)).digest('hex');
const browserCandidates = process.platform === 'win32'
  ? [process.env.PROGRAMFILES, process.env['PROGRAMFILES(X86)'], process.env.LOCALAPPDATA]
      .filter((base): base is string => Boolean(base))
      .map(base => path.join(base, 'Google', 'Chrome', 'Application', 'chrome.exe'))
  : [];
const browserExecutable = process.env.REMOTION_BROWSER_EXECUTABLE || browserCandidates.find(existsSync) || null;
if (browserExecutable && !existsSync(browserExecutable)) throw new Error('REMOTION_BROWSER_EXECUTABLE does not exist.');
if (config.music.path && !existsSync(path.resolve('public', config.music.path))) throw new Error('Configured local music file is missing from public/.');
console.log(`Browser: ${browserExecutable ? 'installed/explicit Chrome' : 'Remotion managed browser'}.`);
console.log('Bundling only the 15-second preview.');
// A small preview does not need persistent webpack cache. This also avoids stale
// cache packs when a project is copied to another machine or dependency location.
const serveUrl = await bundle({entryPoint:path.resolve('src/index.ts'), outDir:path.resolve('build'), enableCaching:false});
console.log('Bundle ready; opening render browser.');
// Current installed Chrome requires --headless=new; managed headless-shell has
// its own mode. Selecting the mode prevents an obsolete --headless=old launch.
const browser = await openBrowser('chrome', {browserExecutable, chromeMode:browserExecutable ? 'chrome-for-testing' : 'headless-shell'});
try {
  const composition = await selectComposition({serveUrl, id:'MathPreview', puppeteerInstance:browser});
  const keyframes = [0, 30, 75, 105, 120, 150, 165, 180, 299, 300, 449];
  for (const frame of keyframes) {
    await renderStill({serveUrl, composition, puppeteerInstance:browser, frame, imageFormat:'png', output:path.join(output, 'keyframes', `frame-${String(frame).padStart(4, '0')}.png`)});
    console.log(`Keyframe ${frame}/${composition.durationInFrames - 1}`);
  }
  const repeat = path.resolve('qa/repeat-frame-0105.png');
  await renderStill({serveUrl, composition, puppeteerInstance:browser, frame:105, imageFormat:'png', output:repeat});
  const deterministic = hash(repeat) === hash(path.join(output, 'keyframes/frame-0105.png'));
  if (!deterministic) throw new Error('Repeated frame 105 differs.');
  const video = path.join(output, 'math-preview-15s.mp4');
  let metadata: Awaited<ReturnType<typeof getVideoMetadata>> | null = null;
  if (!stillsOnly) {
    let last = -1;
    await renderMedia({serveUrl, composition, puppeteerInstance:browser,
      outputLocation:video, codec:'h264', crf:18, pixelFormat:'yuv420p', colorSpace:'bt709', imageFormat:'png',
      audioCodec:'aac', audioBitrate:'192k', sampleRate:48000, concurrency:4,
      onProgress:({progress}) => {const decile = Math.floor(progress * 10); if (decile !== last) {last = decile; console.log(`Render ${decile * 10}%`);}},
    });
    metadata = await getVideoMetadata(video);
    if (metadata.width !== composition.width || metadata.height !== composition.height) throw new Error('Encoded dimensions differ.');
  }
  writeFileSync('qa/render-check.json', JSON.stringify({
    passed:true, previewOnly:true, fullEpisodeRendered:false,
    composition:{id:composition.id, width:composition.width, height:composition.height, fps:composition.fps, frames:composition.durationInFrames},
    renderedVideo:!stillsOnly, keyframes, repeatedFrame105Identical:deterministic,
    browser:browserExecutable ? 'installed-or-explicit-chrome' : 'remotion-managed',
    audio:config.music.path ? {kind:'user-configured-local-file', offsetSeconds:config.music.offsetSeconds, sampleRate:48000} : {kind:'silent'},
    metadata, sha256:stillsOnly ? null : hash(video),
    manualVisualInspection:false, actualListening:false, phoneDevicePlayback:false,
  }, null, 2));
  console.log(stillsOnly ? 'Keyframes ready; no MP4 rendered.' : '15-second MP4 and keyframes ready. Manual review remains required.');
} finally {
  await browser.close({silent:true});
}
