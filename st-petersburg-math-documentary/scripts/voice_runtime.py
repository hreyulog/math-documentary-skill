"""Word-boundary TTS, complete-scene caches, and sample-aligned PCM assembly.

Uses edge_tts only for build-voice. Existing complete WAV + measured subtitles
can be supplied instead. Token coverage and duration tests detect truncation;
they are provenance/timing checks, not an independent ASR transcript.
"""
from __future__ import annotations
import array, asyncio, importlib.metadata, json, math, re, time, unicodedata
from pathlib import Path
from runtime_support import RATE,FPS,canonical_pcm,fingerprint,read_pcm,resolve,run,save,sha,write_pcm

SCHEMA='portable-wordboundary-1'

def plain(text):return ''.join(c for c in unicodedata.normalize('NFKC',text) if c.isalnum())

def cues_for(scene):
 cues=scene.get('cues')
 if not cues:raise ValueError('Each scene requires aligned cues with text/english (or zh/en).')
 result=[]
 for c in cues:
  text=c.get('text',c.get('zh',''));english=c.get('english',c.get('en',''))
  if not text:raise ValueError('Empty Chinese cue')
  result.append(dict(text=text,english=english,speak=c.get('speak',text)))
 return result

def voice_request_key(project,edition,base):
 spec=project['editions'][edition]
 config={k:spec.get(k) for k in ('voice','target_duration','before_pause','after_pause','min_tempo','max_tempo','duration_range')}
 config['project_voice']=project.get('voice',{})
 config['scenes']=[{k:s.get(k) for k in ('id','narration','cues','duration')} for s in spec['scenes']]
 if spec.get('voice_wav'):config['provided_wav_sha256']=sha(resolve(base,spec['voice_wav']))
 if isinstance(spec.get('subtitles'),str):config['provided_subtitle_sha256']=sha(resolve(base,spec['subtitles']))
 elif spec.get('subtitles'):config['provided_subtitles']=spec['subtitles']
 return fingerprint(config)

def mark_ranges(marks,narration):
 reference=plain(narration);cursor=0;result=[]
 for m in marks:
  token=plain(m['text'])
  if not token:continue
  at=reference.find(token,cursor)
  if at<0:raise ValueError(f'WordBoundary token cannot match narration: {token!r} at {cursor}')
  if at!=cursor:raise ValueError(f'WordBoundary skipped narration at {cursor}: {reference[cursor:at]!r}')
  result.append(dict(**m,char_start=at,char_end=at+len(token)));cursor=at+len(token)
 if cursor!=len(reference):raise ValueError(f'TTS did not cover the end of the narration: {cursor}/{len(reference)}')
 return result

async def synthesize(text,path,marks_path,options):
 import edge_tts
 communicator=edge_tts.Communicate(text,voice=options['name'],rate=options['rate'],
                                   pitch=options['pitch'],volume=options['volume'],boundary='WordBoundary')
 marks=[]
 with path.open('wb') as f:
  async for part in communicator.stream():
   if part['type']=='audio':f.write(part['data'])
   elif part['type']=='WordBoundary':
    marks.append(dict(offset=part['offset']/1e7,duration=part['duration']/1e7,text=part['text']))
 save(marks_path,marks)

def synth_scene(scene,folder,index,ffmpeg,options,retries=3):
 cues=cues_for(scene);text=scene.get('narration') or ''.join(c['speak'] for c in cues)
 if plain(text)!=plain(''.join(c['speak'] for c in cues)):
  raise ValueError('Scene narration must match the concatenated cue.speak/text.')
 try:version=importlib.metadata.version('edge_tts')
 except importlib.metadata.PackageNotFoundError:version='unavailable'
 key=fingerprint(dict(schema=SCHEMA,text=text,options=options,edge_tts=version))
 stem=f'{index:02}-{key[:16]}'
 mp3=folder/(stem+'.mp3');marks_path=folder/(stem+'-marks.json');wav=folder/(stem+'-raw.wav');receipt=folder/(stem+'-cache.json')
 errors=[]
 for attempt in range(retries):
  try:
   reusable=False
   if receipt.exists():
    old=json.loads(receipt.read_text('utf-8'))
    reusable=old.get('key')==key and all(p.exists() and sha(p)==old.get(k) for p,k in ((mp3,'mp3_sha256'),(marks_path,'marks_sha256'),(wav,'wav_sha256')))
   if not reusable:
    asyncio.run(synthesize(text,mp3,marks_path,options));canonical_pcm(ffmpeg,mp3,wav)
   samples=read_pcm(wav);duration=len(samples)/RATE
   marks=json.loads(marks_path.read_text('utf-8'));ranges=mark_ranges(marks,text)
   if not ranges:raise ValueError('No usable WordBoundary marks returned')
   if duration<len(plain(text))/9:raise ValueError('Audio unusually short for narration: possible truncated TTS response')
   word_end=max(m['offset']+m['duration'] for m in ranges)
   if word_end>duration+.25:raise ValueError(f'WordBoundary extends beyond decoded audio: {word_end:.3f}/{duration:.3f}')
   # Packet boundary clocks can differ slightly from decoder length. A gross
   # mismatch fails; small clock differences are recorded, not hidden.
   if word_end<duration-1.4:raise ValueError('Unexplained audio after final word boundary')
   save(receipt,dict(schema=SCHEMA,key=key,text_sha256=fingerprint(text),voice=options,
                    edge_tts=version,mp3_sha256=sha(mp3),marks_sha256=sha(marks_path),
                    wav_sha256=sha(wav),pcm_seconds=duration,last_word_end=word_end,
                    token_coverage='complete',not_asr=True,retries=errors))
   return cues,text,ranges,samples,dict(cache=str(receipt),raw_wav=str(wav),raw_sha256=sha(wav),duration=duration)
  except Exception as exc:
   errors.append(str(exc))
   if receipt.exists():receipt.unlink()
   if attempt+1==retries:raise RuntimeError(f'Scene {index} TTS failed after {retries} attempts: {errors}') from exc
   time.sleep(min(2*(attempt+1),5))

def build_voice(project,edition,ffmpeg,build,base):
 from runtime_support import resolve
 spec=project['editions'][edition];scenes=spec['scenes'];build=Path(build);build.mkdir(parents=True,exist_ok=True)
 existing=spec.get('voice_wav')
 if existing:
  source=resolve(base,existing);canonical_pcm(ffmpeg,source,build/'voice-raw.wav')
  samples=read_pcm(build/'voice-raw.wav');duration=len(samples)/RATE
  frame_count=round(duration*FPS)
  if abs(duration-frame_count/FPS)>.00003:raise ValueError('Existing WAV must end on the 24fps sample grid; supply scene durations and pad it without cutting speech.')
  raw_cues=spec.get('subtitles')
  if isinstance(raw_cues,str):raw_cues=json.loads(resolve(base,raw_cues).read_text('utf-8-sig'))
  if isinstance(raw_cues,dict):raw_cues=raw_cues.get('subtitles')
  if not isinstance(raw_cues,list):raise ValueError('Existing WAV requires measured subtitle JSON; character timing is not accepted.')
  durations=[s.get('duration') for s in scenes]
  if any(x is None for x in durations) or abs(sum(durations)-duration)>1/FPS:
   raise ValueError('Existing WAV requires all scene durations, summing to its decoded length.')
  cursors=[];start=0
  for i,(s,d) in enumerate(zip(scenes,durations)):
   frames=round(d*FPS)
   if abs(d-frames/FPS)>.00003:raise ValueError('Scene durations must align to 24fps.')
   cursors.append(dict(index=i,id=s.get('id',str(i)),start=start,duration=d));start+=d
  captions=[]
  for c in raw_cues:
   captions.append(dict(start=c['start'],end=c['end'],scene=c['scene'],text=c.get('text',c.get('zh')),english=c.get('english',c.get('en',''))))
  provenance=dict(method='provided measured WAV/cues',source=str(source),source_sha256=sha(source),not_asr=True)
 else:
  options=dict(name='zh-CN-YunxiNeural',rate='+0%',pitch='+0Hz',volume='+0%')
  options.update(project.get('voice',{}));options.update(spec.get('voice',{}))
  folder=build/'voice-cache';folder.mkdir(exist_ok=True)
  inputs=[synth_scene(s,folder,i,ffmpeg,options) for i,s in enumerate(scenes)]
  before=float(spec.get('before_pause',.18));after=float(spec.get('after_pause',.32))
  target=spec.get('target_duration',90 if edition=='short' else None)
  raw_total=sum(len(x[3])/RATE for x in inputs)
  tempo=1.0
  if target is not None:
   target_frames=round(float(target)*FPS)
   if target_frames<=0:raise ValueError('Target duration must be positive')
   speech_budget=target_frames/FPS-len(scenes)*(before+after+1/FPS)
   if speech_budget<=0:raise ValueError('Target too short for scene pauses')
   tempo=raw_total/speech_budget
   minimum=float(spec.get('min_tempo',.90));maximum=float(spec.get('max_tempo',1.10))
   if not 0.5<=minimum<=maximum<=2.0:raise ValueError('Explicit tempo bounds must remain between .5 and 2.0')
   if not minimum<=tempo<=maximum:
    allowed=spec.get('duration_range')
    if allowed and len(allowed)==2:
     natural_tempo=max(minimum,min(maximum,tempo))
     natural_target=raw_total/natural_tempo+len(scenes)*(before+after+1/FPS)
     natural_frames=math.floor(natural_target*FPS) if tempo<minimum else math.ceil(natural_target*FPS)
     if float(allowed[0])<=natural_frames/FPS<=float(allowed[1]):
      target_frames=natural_frames;speech_budget=target_frames/FPS-len(scenes)*(before+after+1/FPS)
      tempo=raw_total/speech_budget
    if not minimum<=tempo<=maximum:raise ValueError(f'Target would require tempo {tempo:.3f}; edit narration or target duration (default natural bounds .90..1.10).')
  transformed=[];durations=[]
  for i,item in enumerate(inputs):
   path=build/f'voice-tempo-{i:02}.wav'
   canonical_pcm(ffmpeg,item[4]['raw_wav'],path,f'atempo={tempo:.10f}')
   data=read_pcm(path);transformed.append(data)
   durations.append(math.ceil((len(data)/RATE+before+after)*FPS)/FPS)
  if target is not None:
   remaining=target_frames-sum(round(d*FPS) for d in durations)
   if remaining<0:raise ValueError('Tempo output exceeds target; speech was not cut. Increase target by a small amount.')
   durations[-1]+=remaining/FPS
  samples=array.array('h');captions=[];cursors=[];start=0.0
  for i,(scene,item,data,duration) in enumerate(zip(scenes,inputs,transformed,durations)):
   cues,text,marks,_,receipt=item;scene_samples=round(duration*RATE);pad=round(before*RATE)
   block=array.array('h',[0])*scene_samples
   if pad+len(data)>scene_samples:raise ValueError('Speech does not fit; refusing to truncate')
   block[pad:pad+len(data)]=data;samples.extend(block)
   pointer=0
   for cue in cues:
    chars=plain(cue['speak']);finish=pointer+len(chars)
    relevant=[m for m in marks if m['char_end']>pointer and m['char_start']<finish]
    if not relevant:raise ValueError(f'No measured boundary for cue: {cue["text"]}')
    a=start+before+relevant[0]['offset']/tempo
    b=start+before+(relevant[-1]['offset']+relevant[-1]['duration'])/tempo
    if captions and captions[-1]['scene']==i and a<captions[-1]['end']:
     # A provider word spans a cue boundary. Reject rather than invent a split.
     raise ValueError('Cue boundary cuts a provider token; join those cues or choose a punctuation boundary.')
    if b>start+duration:raise ValueError('Measured cue extends beyond scene')
    captions.append(dict(start=a,end=b,scene=i,text=cue['text'],english=cue['english']))
    pointer=finish
   cursors.append(dict(index=i,id=scene.get('id',str(i)),start=start,duration=duration,
                       speech_seconds=len(data)/RATE,cache=receipt))
   start+=duration
  duration=len(samples)/RATE
  provenance=dict(method='edge_tts WordBoundary',voice=options,tempo=tempo,requested_duration=target,
                  actual_duration=duration,token_coverage='complete',not_asr=True)
  write_pcm(build/'voice-raw.wav',samples)
 # Normalize voice separately in a completed PCM pass; length remains exact.
 normalized=build/'voice-normalized-temp.wav'
 canonical_pcm(ffmpeg,build/'voice-raw.wav',normalized,'loudnorm=I=-17:TP=-2:LRA=7')
 normalized_samples=read_pcm(normalized)
 if abs(len(normalized_samples)-len(samples))>RATE//20:raise ValueError('Voice loudness pass changed duration unexpectedly')
 if len(normalized_samples)<len(samples):normalized_samples.extend(array.array('h',[0])*(len(samples)-len(normalized_samples)))
 normalized_samples=normalized_samples[:len(samples)]
 write_pcm(build/'voice.wav',normalized_samples)
 timeline=dict(schema='portable-documentary-timeline-1',edition=edition,fps=FPS,duration=duration,
               scenes=cursors,subtitles=captions,voice_path=str(build/'voice.wav'),voice_sha256=sha(build/'voice.wav'),
               sample_rate=RATE,samples=len(samples),provenance=provenance,
               voice_request_sha256=voice_request_key(project,edition,base))
 save(build/'voice-timeline.json',timeline)
 return timeline
