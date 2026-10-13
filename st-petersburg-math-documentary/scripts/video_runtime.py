"""Portable 9:16 documentary runtime, driven only by a project JSON.

doctor / build-voice / prepare / preview / render / verify / build
All paths in a project are relative to that project, not to this script.
Automatic verification is technical evidence; human visual/fact review remains
pending until separately recorded. No external license is inferred or verified.
"""
from __future__ import annotations
import argparse,array,bisect,importlib.util,json,math,os,re,shutil,subprocess,sys
sys.dont_write_bytecode=True
from fractions import Fraction
from pathlib import Path
from runtime_support import FPS,RATE,canonical_pcm,faststart,find_ffmpeg,fingerprint,probe,read_pcm,resolve,run,save,sha,timestamp,write_pcm

VERSION='portable-documentary-1'
W,H=1080,1920
WINDOW=(56,462,912,1280)
PANEL=(50,1330,914,1570)

def context(project_path,ffmpeg=None):
 path=Path(project_path).expanduser().resolve();project=json.loads(path.read_text('utf-8-sig'))
 if project.get('schema')!='portable-documentary-project-1':raise ValueError('Unsupported project schema')
 if not project.get('editions'):raise ValueError('No editions defined')
 base=path.parent;output=resolve(base,project.get('output_dir','output'))
 assets=project.get('assets',{})
 if isinstance(assets,list):assets={a['id']:a for a in assets}
 project['assets']=assets
 return dict(path=path,project=project,base=base,output=output,ffmpeg=find_ffmpeg(ffmpeg))

def font_path(value='auto'):
 if value!='auto':
  path=Path(value)
  if not path.is_file():raise FileNotFoundError(path)
  return path
 windir=Path(os.environ.get('WINDIR',os.environ.get('SystemRoot','C:/Windows')))
 candidates=[windir/'Fonts/msyh.ttc',windir/'Fonts/simhei.ttf',Path('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'),Path('/System/Library/Fonts/PingFang.ttc')]
 for path in candidates:
  if path.is_file():return path
 raise RuntimeError('A CJK font was not found. Set style.font and style.english_font to installed font files.')

class Layout:
 def __init__(self,ctx):
  from PIL import ImageFont
  self.ctx=ctx;self.style=ctx['project'].get('style',{});self.fonts={}
  cn_value=self.style.get('font','auto');en_value=self.style.get('english_font','auto')
  self.cn_path=font_path(str(resolve(ctx['base'],cn_value)) if cn_value!='auto' else 'auto')
  self.en_path=font_path(str(resolve(ctx['base'],en_value)) if en_value!='auto' else str(self.cn_path))
  self.cn_bold=bool(self.style.get('chinese_bold',self.cn_path.name.lower().startswith('msyh')))
  bold=self.cn_path.with_name('msyhbd.ttc')
  if self.cn_bold and self.cn_path.name.lower()=='msyh.ttc' and bold.exists():self.cn_path=bold
  self.bg=self.style.get('background','#11191c');self.accent=self.style.get('accent','#e5bd7f')
  self.cn_size=int(self.style.get('font_size',52));self.en_size=int(self.style.get('english_size',34))
  self.white='#f5f1e8';self.muted='#aeb8b7';self.green='#99d3b7';self.panel='#1e2b2e'
  for path in (self.cn_path,self.en_path):
   if not path.is_absolute():raise ValueError('Resolved font path must be absolute')
 def face(self,size,english=False):
  from PIL import ImageFont
  key=(size,english)
  if key not in self.fonts:self.fonts[key]=ImageFont.truetype(str(self.en_path if english else self.cn_path),size)
  return self.fonts[key]
 def rows(self,value,size,width=820,english=False,max_rows=None):
  font=self.face(size,english);result=[]
  for paragraph in str(value).split('\n'):
   if not english:
    if not paragraph:continue
    if font.getlength(paragraph)<=width:result.append(paragraph);continue
    closing=set('，。！？；：、）］】》〉”’」』〕〗〙〛…％‰')
    opening=set('（［【《〈“‘「『〔〖〘〚')
    ranges=[m.span() for m in re.finditer(r'《[^《》]+》(?:中|里)?|[A-Za-z0-9]+(?:[._\'’:-][A-Za-z0-9]+)*(?:年|岁|秒|分钟|小时|%|％)?',paragraph)]
    protected=self.style.get('protected_terms',[])
    protected=[protected] if isinstance(protected,str) else list(protected)
    person=self.ctx['project'].get('person',{})
    name=person.get('name','') if isinstance(person,dict) else str(person)
    if name:
     protected.extend([name,re.split(r'[·•]',name)[-1]])
    for term in protected:
     if term:ranges.extend(m.span() for m in re.finditer(re.escape(str(term)),paragraph))
    candidates=[]
    for index in range(1,len(paragraph)):
     if paragraph[index] in closing or paragraph[index-1] in opening:continue
     if any(a<index<b for a,b in ranges):continue
     left,right=paragraph[:index],paragraph[index:]
     a,b=font.getlength(left),font.getlength(right)
     if a>width or b>width:continue
     punctuation_bonus=180 if left[-1] in '，。！？；：、' else 0
     score=abs(a-b)+max(a,b)*.20-punctuation_bonus
     candidates.append((score,left,right))
    if not candidates:raise ValueError(f'Chinese cannot fit two legal lines without splitting a protected term: {paragraph!r}')
    _,left,right=min(candidates);result.extend([left,right]);continue
   units=paragraph.split() if english else list(paragraph);row=''
   for unit in units:
    proposed=(row+' '+unit).strip() if english else row+unit
    if row and font.getlength(proposed)>width:result.append(row);row=unit
    else:row=proposed
   if row:result.append(row)
  limit=max_rows if max_rows is not None else (2 if not english else None)
  if limit and len(result)>limit:raise ValueError(f'Text exceeds {limit} lines: {value!r}')
  if any(font.getlength(row)>width for row in result):raise ValueError(f'A word cannot fit: {value!r}')
  return result
 def text(self,draw,xy,value,size,color=None,english=False,anchor=None):
  draw.text(xy,str(value),font=self.face(size,english),fill=color or self.white,anchor=anchor,stroke_width=1 if size>=42 else 0,stroke_fill=self.bg)
 def label(self,shot):
  asset=self.ctx['project']['assets'].get(shot.get('asset'),{})
  value=shot.get('caption_label',asset.get('caption_label',''))
  if asset.get('source_class')=='ai_generated':
   value='AI情景再现 · 非历史影像'+(' · '+value if value and 'AI' not in value else '')
  return value or ('原创数学示意 · 非采样结果' if shot['type']=='diagram' else '资料镜头 · 来源见署名' if shot.get('asset') else '事实卡 · 非历史影像')
 def header(self,scene,shot,transparent=False):
  from PIL import Image,ImageDraw
  im=Image.new('RGBA' if transparent else 'RGB',(W,H),self.bg);d=ImageDraw.Draw(im)
  if transparent:d.rectangle(WINDOW,fill=(0,0,0,0))
  self.text(d,(60,148),self.ctx['project'].get('title','数学人物'),27,self.muted)
  for i,row in enumerate(self.rows(scene['headline'],62,840,max_rows=2)):
   self.text(d,(60,220+i*82),row,62,self.white if i==0 else self.accent)
  for i,row in enumerate(self.rows(self.label(shot),25,820,max_rows=2)):
   self.text(d,(60,388+i*34),row,25,self.muted)
  return im
 def subtitles(self,im,cue):
  from PIL import ImageDraw
  d=ImageDraw.Draw(im);cn=self.rows(cue['text'],self.cn_size,max_rows=2)
  en=self.rows(cue.get('english',''),self.en_size,english=True,max_rows=2)
  height=len(cn)*64+(12 if en else 0)+len(en)*43;y=PANEL[1]+(PANEL[3]-PANEL[1]-height)/2
  d.rounded_rectangle(PANEL,18,fill='#050c10')
  for i,row in enumerate(cn):self.text(d,(482,y+i*64),row,self.cn_size,anchor='mt')
  for i,row in enumerate(en):self.text(d,(482,y+len(cn)*64+12+i*43),row,self.en_size,'#e1c79b',True,'mt')
  return im

def asset(ctx,identifier):
 if identifier not in ctx['project']['assets']:raise KeyError(f'Unknown asset ID {identifier}')
 item=dict(ctx['project']['assets'][identifier]);item['id']=identifier
 item['credit']=item.get('credit',item.get('creator',item.get('author','')))
 item['caption_label']=item.get('caption_label',item.get('label',''))
 item['page']=item.get('page',item.get('source_url',item.get('url','')))
 item['path']=str(resolve(ctx['base'],item['path']))
 if not Path(item['path']).is_file():raise FileNotFoundError(item['path'])
 if not item.get('credit') or not item.get('license'):raise ValueError(f'Asset {identifier} lacks credit/license declaration')
 if re.search(r'placeholder|填写|example|待核',str(item['license']),re.I):raise ValueError(f'Unresolved license declaration: {identifier}')
 item['sha256']=sha(item['path'])
 return item

def edition_dir(ctx,edition):return ctx['output']/'build'/edition

def build_voice(ctx,edition):
 from voice_runtime import build_voice as make_voice
 return make_voice(ctx['project'],edition,ctx['ffmpeg'],edition_dir(ctx,edition),ctx['base'])

def mix_audio(ctx,edition,timeline,build):
 source=read_pcm(build/'voice.wav');master=array.array('h',source);music=ctx['project']['editions'][edition].get('music',ctx['project'].get('music'))
 receipt={'voice_sha256':sha(build/'voice.wav'),'method':'offline sample-aligned PCM','samples':len(master),'music':None,'clipped_samples':0}
 if music:
  selected=asset(ctx,music['asset'])
  if selected['type']!='audio':raise ValueError('Music asset must be type audio')
  canonical_pcm(ctx['ffmpeg'],selected['path'],build/'music-pcm.wav');bg=read_pcm(build/'music-pcm.wav')
  gain=float(music.get('volume',.06));duck=float(music.get('duck',.5))
  if not 0<=gain<=.30 or not 0<=duck<=1:raise ValueError('Music volume/duck is outside supported bounds')
  if not bg:raise ValueError('Empty music PCM')
  loop=bool(music.get('loop',False));ranges=[(round(c['start']*RATE),round(c['end']*RATE)) for c in timeline['subtitles']]
  pointer=0;clipped=0
  for i in range(len(master)):
   while pointer<len(ranges) and i>=ranges[pointer][1]:pointer+=1
   talking=pointer<len(ranges) and ranges[pointer][0]<=i<ranges[pointer][1]
   value=bg[i%len(bg)] if loop or i<len(bg) else 0
   fade=min(1,i/RATE,(len(master)-1-i)/RATE)
   mixed=round(master[i]+value*gain*(duck if talking else 1)*fade)
   if abs(mixed)>32767:clipped+=1
   master[i]=max(-32768,min(32767,mixed))
  if clipped:raise ValueError(f'Mix clips {clipped} samples. Reduce music/voice level; no clipped mix exported.')
  receipt['music']=dict(id=music['asset'],source_sha256=selected['sha256'],credit=selected['credit'],license_declared=selected['license'],external_license_verified=False,volume=gain,duck=duck,loop=loop)
 write_pcm(build/'mixed.wav',master);receipt['mixed_sha256']=sha(build/'mixed.wav');save(build/'mix-receipt.json',receipt)
 return receipt

def prepare(ctx,edition):
 build=edition_dir(ctx,edition);build.mkdir(parents=True,exist_ok=True)
 voice=build/'voice-timeline.json'
 if not voice.exists():build_voice(ctx,edition)
 timeline=json.loads(voice.read_text('utf-8'));spec=ctx['project']['editions'][edition];layout=Layout(ctx)
 from voice_runtime import voice_request_key
 if timeline.get('voice_request_sha256')!=voice_request_key(ctx['project'],edition,ctx['base']):
  raise ValueError('Voice/cue configuration changed; run build-voice again. Unchanged scene TTS caches will be reused.')
 if len(timeline['scenes'])!=len(spec['scenes']):raise ValueError('Voice/project scene count differs; run build-voice again')
 inputs={};shots=[];counter=0
 for i,(timing,scene) in enumerate(zip(timeline['scenes'],spec['scenes'])):
  layout.rows(scene['headline'],62,840,max_rows=2)
  plan=scene.get('shots')
  if not plan:raise ValueError(f'Scene {i} has no shots')
  frame_budget=round(timing['duration']*FPS);fixed=[];free=[]
  for j,s in enumerate(plan):
   if 'duration' in s:
    n=round(float(s['duration'])*FPS)
    if abs(n/FPS-float(s['duration']))>1e-5:raise ValueError('Fixed shot duration must align to 24fps')
    fixed.append((j,n))
   else:free.append((j,float(s.get('weight',1))))
  remaining=frame_budget-sum(n for _,n in fixed)
  if remaining<0 or (not free and remaining):raise ValueError(f'Shot durations do not fill scene {i}')
  allocation=dict(fixed)
  if free:
   weight=sum(w for _,w in free)
   if any(w<=0 for _,w in free):raise ValueError('Shot weights must be positive')
   parts=[math.floor(remaining*w/weight) for _,w in free]
   for k in range(remaining-sum(parts)):parts[k%len(parts)]+=1
   allocation.update({j:n for (j,_),n in zip(free,parts)})
  start=timing['start']
  for j,s in enumerate(plan):
   shot=dict(s);frames=allocation[j]
   if frames<=0:raise ValueError('Shot is too short to receive a frame')
   shot.update(index=counter,scene=i,start=start,duration=frames/FPS,frames=frames)
   kind=shot['type']
   if kind not in {'video','image','card','diagram'}:raise ValueError(f'Unsupported shot type {kind}')
   if shot.get('crop') or shot.get('framing') in {'crop','cover'}:
    raise ValueError('This runtime supports full-source contain only; cropping/watermark removal is not supported.')
   if shot.get('asset'):
    selected=asset(ctx,shot['asset']);inputs[shot['asset']]=selected
    if kind=='video':
     if selected['type']!='video':raise ValueError('Video shot refers to non-video asset')
     metadata=probe(ctx['ffmpeg'],selected['path']);offset=float(shot.get('source_start',0))
     if offset<0 or metadata['duration'] is None or offset+shot['duration']>metadata['duration']+.001:
      raise ValueError(f'Video trim exceeds source: {shot["asset"]} {offset}+{shot["duration"]}/{metadata["duration"]}')
     shot['source_start']=offset;shot['source_duration']=metadata['duration'];shot['source_class']=selected.get('source_class','user_declared_real_video')
    elif selected['type']!='image':raise ValueError('Still/card shot requires an image asset')
   elif kind in {'video','image'}:raise ValueError('Video/image shot needs asset ID')
   if kind=='diagram':validate_diagram(shot.get('diagram',{}))
   if kind=='card' and not shot.get('asset'):
    title_rows=layout.rows(shot.get('title',''),62,740,max_rows=2)
    line_count=sum(len(layout.rows(line,46,740)) for line in shot.get('lines',[]))
    if 620+len(title_rows)*80+line_count*70>1250:raise ValueError('Card body does not fit the content area')
   layout.rows(layout.label(shot),25,820,max_rows=2)
   shots.append(shot);counter+=1;start+=frames/FPS
 for c in timeline['subtitles']:
  if not 0<=c['start']<c['end']<=timeline['duration']:raise ValueError('Invalid subtitle timing')
  layout.rows(c['text'],layout.cn_size,max_rows=2);layout.rows(c.get('english',''),layout.en_size,english=True,max_rows=2)
  scene=timeline['scenes'][c['scene']]
  if c['start']<scene['start']-.001 or c['end']>scene['start']+scene['duration']+.001:raise ValueError('Subtitle crosses scene boundary')
 previous=0
 for c in timeline['subtitles']:
  if c['start']<previous-.001:raise ValueError('Overlapping subtitles')
  previous=c['end']
 receipt=mix_audio(ctx,edition,timeline,build)
 timeline.update(project_sha256=sha(ctx['path']),render_version=VERSION,shots=shots,assets=inputs,mix=receipt,
                 runtime_script_sha256=sha(__file__),
                 style=ctx['project'].get('style',{}),font=str(layout.cn_path),english_font=str(layout.en_path),
                 mobile_layout={'caption_panel':list(PANEL),'right_reserved_pixels':166,'bottom_reserved_pixels':350,'note':'Design margins; platform/device overlays can differ.'})
 save(build/'timeline.json',timeline);write_subtitles(ctx,edition,timeline,layout)
 selected={k:v for k,v in inputs.items()}
 if receipt['music']:selected[receipt['music']['id']]=asset(ctx,receipt['music']['id'])
 save(ctx['output']/'delivery'/f'{edition}-attributions.json',dict(assets=selected,external_license_review='pending human review; declarations are not independently verified'))
 print(f'PREPARED {edition}: {timeline["duration"]:.3f}s, {len(shots)} shots, {len(timeline["subtitles"])} cues',flush=True)
 return timeline

def ass_time(value):
 n=round(value*100);h,n=divmod(n,360000);m,n=divmod(n,6000);s,n=divmod(n,100)
 return f'{h}:{m:02}:{s:02}.{n:02}'

def ass_escape(text):return str(text).replace('\\','\\\\').replace('{',r'\{').replace('}',r'\}').replace('\n',r'\N')

def write_subtitles(ctx,edition,timeline,layout):
 build=edition_dir(ctx,edition);out=ctx['output']/'delivery';out.mkdir(parents=True,exist_ok=True)
 styles='[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\nScaledBorderAndShadow: yes\n\n[V4+ Styles]\nFormat: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding\n'
 cn_name=layout.face(layout.cn_size).getname()[0];en_name=layout.face(layout.en_size,True).getname()[0]
 # libass nominal em sizes differ from Pillow glyph sizes for Windows YaHei.
 # Keep the demonstrated YaHei calibration; other families require an actual
 # encoded-frame review or explicit style.ass_*_size calibration.
 yahei_cn='yahei' in cn_name.lower().replace(' ','');yahei_en='yahei' in en_name.lower().replace(' ','')
 ass_cn=int(layout.style.get('ass_chinese_size',round(layout.cn_size*64/52) if yahei_cn else layout.cn_size))
 ass_en=int(layout.style.get('ass_english_size',round(layout.en_size*44/34) if yahei_en else layout.en_size))
 styles+=f'Style: CN,{cn_name},{ass_cn},&H00E8F1F5,&H00E8F1F5,&H00100C05,&H00100C05,{-1 if layout.cn_bold else 0},0,0,0,100,100,0,0,1,1,0,8,0,0,0,1\n'
 styles+=f'Style: EN,{en_name},{ass_en},&H009BC7E1,&H009BC7E1,&H00100C05,&H00100C05,0,0,0,0,100,100,0,0,1,1,0,8,0,0,0,1\n\n[Events]\nFormat: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n'
 save(build/'font-calibration.json',dict(pillow_chinese=layout.cn_size,pillow_english=layout.en_size,ass_chinese=ass_cn,ass_english=ass_en,chinese_bold=layout.cn_bold,font_families=[cn_name,en_name],calibration='prior measured YaHei em/glyph correction' if yahei_cn and yahei_en else 'explicit or uncalibrated font family; encoded visual review required',encoded_visual_review='pending'))
 events=[];bilingual=[];english=[];chinese=[]
 for i,c in enumerate(timeline['subtitles'],1):
  cn=layout.rows(c['text'],layout.cn_size,max_rows=2);en=layout.rows(c.get('english',''),layout.en_size,english=True,max_rows=2)
  height=len(cn)*64+(12 if en else 0)+len(en)*43;y=PANEL[1]+(240-height)/2
  a,b=ass_time(c['start']),ass_time(c['end'])
  drawing=r'{\an7\pos(0,0)\p1\bord0\shad0\1c&H100C05&}m 50 1330 l 914 1330 914 1570 50 1570{\p0}'
  events.append(f'Dialogue: 0,{a},{b},CN,,0,0,0,,{drawing}')
  for j,row in enumerate(cn):events.append(f'Dialogue: 1,{a},{b},CN,,0,0,0,,{{\\an8\\pos(482,{y+j*64:.2f})}}{ass_escape(row)}')
  for j,row in enumerate(en):events.append(f'Dialogue: 1,{a},{b},EN,,0,0,0,,{{\\an8\\pos(482,{y+len(cn)*64+12+j*43:.2f})}}{ass_escape(row)}')
  timing=f'{i}\n{timestamp(c["start"])} --> {timestamp(c["end"])}\n'
  bilingual.append(timing+c['text']+('\n'+'\n'.join(en) if en else ''))
  english.append(timing+'\n'.join(en));chinese.append(timing+c['text'])
 (build/'subtitles.ass').write_text(styles+'\n'.join(events)+'\n','utf-8-sig')
 for suffix,blocks in [('bilingual',bilingual),('en',english),('zh',chinese)]:
  (out/f'{edition}-{suffix}.srt').write_text('\n\n'.join(blocks)+'\n','utf-8-sig')
 save(build/'subtitles.json',timeline['subtitles'])
 fonts=build/'fonts';fonts.mkdir(exist_ok=True)
 for path in {layout.cn_path,layout.en_path}:shutil.copy2(path,fonts/path.name)

def validate_diagram(diagram):
 if diagram.get('kind')!='transition':raise ValueError('Only transition diagrams are supported')
 states=diagram.get('states');matrix=diagram.get('matrix')
 if not isinstance(states,list) or len(states)!=2:raise ValueError('Transition diagram needs exactly two states')
 if not isinstance(matrix,list) or len(matrix)!=2 or any(len(row)!=2 for row in matrix):raise ValueError('Transition diagram needs a 2x2 matrix')
 for row in matrix:
  if any(not math.isfinite(float(x)) or not 0<=x<=1 for x in row) or abs(sum(row)-1)>1e-8:raise ValueError('Each transition-matrix row must sum to one')

def draw_frame(ctx,scene,shot,elapsed=0):
 from PIL import Image,ImageDraw,ImageOps
 layout=Layout(ctx);im=layout.header(scene,shot);d=ImageDraw.Draw(im)
 if shot['type'] in {'image','video'} or shot.get('asset'):
  selected=asset(ctx,shot['asset'])
  if shot['type']=='video':
   cache=edition_dir(ctx,shot.get('_edition','short'))/'preview-frames';cache.mkdir(parents=True,exist_ok=True)
   image=cache/f'{shot["index"]:03}.png'
   run([ctx['ffmpeg'],'-hide_banner','-loglevel','error','-y','-ss',str(shot['source_start']+elapsed),'-i',selected['path'],'-frames:v','1',image])
   picture=Image.open(image).convert('RGB')
  else:picture=Image.open(selected['path']).convert('RGB')
  picture=ImageOps.contain(picture,(WINDOW[2]-WINDOW[0],WINDOW[3]-WINDOW[1]))
  im.paste(picture,(WINDOW[0]+(WINDOW[2]-WINDOW[0]-picture.width)//2,WINDOW[1]+(WINDOW[3]-WINDOW[1]-picture.height)//2))
 if shot['type']=='card' and not shot.get('asset'):
  d.rounded_rectangle((72,490,910,1250),22,fill=layout.panel)
  title_rows=layout.rows(shot.get('title',''),62,740,max_rows=2)
  for i,row in enumerate(title_rows):layout.text(d,(104,535+i*80),row,62,layout.accent)
  y=620+len(title_rows)*80
  for line in shot.get('lines',[]):
   for row in layout.rows(line,46,740):layout.text(d,(104,y),row,46);y+=70
  if y>1220:raise ValueError('Card text exceeds content area')
 if shot['type']=='diagram':
  diagram=shot['diagram'];validate_diagram(diagram)
  d.rounded_rectangle((72,490,910,1250),22,fill=layout.panel)
  layout.text(d,(104,535),shot.get('title','状态之间的转移'),49,layout.accent)
  for j,x in enumerate((280,684)):
   d.ellipse((x-82,748,x+82,912),fill='#304644',outline=layout.green,width=5)
   layout.text(d,(x,803),diagram['states'][j],52,anchor='mt')
   d.arc((x-70,620,x+70,760),185,535,fill=layout.green,width=5)
   layout.text(d,(x,633),f'{diagram["matrix"][j][j]:.2g}',36,layout.green,True,'mt')
  def curve(t,reverse=False):
   a,b=(604,364) if reverse else (364,604);sign=1 if reverse else -1
   return a+(b-a)*t,850+sign*150*math.sin(math.pi*t)
  for reverse in (False,True):
   points=[curve(i/60,reverse) for i in range(61)]
   d.line(points,fill=layout.accent,width=6)
   end=points[-1];d.polygon([(end[0],end[1]),(end[0]+(18 if reverse else -18),end[1]-14),(end[0]+(18 if reverse else -18),end[1]+14)],fill=layout.accent)
  layout.text(d,(484,678),f'{diagram["matrix"][0][1]:.2g}',38,layout.accent,True,'mt')
  layout.text(d,(484,1010),f'{diagram["matrix"][1][0]:.2g}',38,layout.accent,True,'mt')
  phase=(elapsed/2.0)%2;point=curve(phase if phase<1 else phase-1,phase>=1)
  d.ellipse((point[0]-12,point[1]-12,point[0]+12,point[1]+12),fill=layout.white)
  layout.text(d,(105,1150),'每一行的概率之和为 1',36,layout.muted)
 return im

def load_timeline(ctx,edition):return json.loads((edition_dir(ctx,edition)/'timeline.json').read_text('utf-8'))

def preview(ctx,edition):
 from PIL import Image,ImageDraw
 timeline=load_timeline(ctx,edition);spec=ctx['project']['editions'][edition];build=edition_dir(ctx,edition);folder=build/'preview';folder.mkdir(exist_ok=True)
 layout=Layout(ctx);thumbs=[]
 for s in timeline['shots']:
  shot=dict(s,_edition=edition);mid=shot['duration']/2
  im=draw_frame(ctx,spec['scenes'][shot['scene']],shot,mid)
  at=shot['start']+mid;cue=next((c for c in timeline['subtitles'] if c['start']<=at<c['end']),None)
  if cue:layout.subtitles(im,cue)
  path=folder/f'shot-{shot["index"]:03}.jpg';im.save(path,quality=90)
  thumbs.append(im.resize((216,384)))
 cols=4;sheet=Image.new('RGB',(cols*216,math.ceil(len(thumbs)/cols)*410),layout.bg);d=ImageDraw.Draw(sheet)
 for i,thumb in enumerate(thumbs):
  x=(i%cols)*216;y=(i//cols)*410;sheet.paste(thumb,(x,y));d.text((x+4,y+385),f'Shot {i+1}',fill='white')
 sheet.save(folder/'contact-sheet.jpg',quality=90)
 print('PREVIEW',folder/'contact-sheet.jpg',flush=True)

def filter_path(path):return str(Path(path).resolve()).replace('\\','/').replace(':',r'\:').replace("'",r"\'")

def render(ctx,edition,threads=3):
 timeline=load_timeline(ctx,edition);build=edition_dir(ctx,edition);folder=build/'clips';folder.mkdir(exist_ok=True)
 layout=Layout(ctx);spec=ctx['project']['editions'][edition];ff=ctx['ffmpeg'];clips=[]
 if timeline.get('project_sha256')!=sha(ctx['path']) or timeline.get('runtime_script_sha256')!=sha(__file__):
  raise ValueError('Project/renderer changed after prepare; run prepare again before encoding')
 if sha(build/'mixed.wav')!=timeline['mix']['mixed_sha256']:raise ValueError('Mixed audio changed after prepare')
 for item in timeline['assets'].values():
  if sha(item['path'])!=item['sha256']:raise ValueError('Media source changed after prepare')
 for s in timeline['shots']:
  shot=dict(s,_edition=edition);scene=spec['scenes'][shot['scene']]
  inputs={shot['asset']:timeline['assets'][shot['asset']]['sha256']} if shot.get('asset') else {}
  selected_asset=ctx['project']['assets'].get(shot.get('asset'),{})
  key=fingerprint(dict(version=VERSION,script=sha(__file__),style=layout.style,shot=shot,
                       global_title=ctx['project'].get('title'),scene_headline=scene['headline'],
                       source_label=layout.label(shot),source_class=selected_asset.get('source_class'),
                       assets=inputs,font=sha(layout.cn_path),english_font=sha(layout.en_path)))
  clip=folder/f'{shot["index"]:03}-{key[:12]}.mp4';receipt=clip.with_suffix('.json')
  if clip.exists() and receipt.exists() and json.loads(receipt.read_text('utf-8')).get('sha256')==sha(clip):
   clips.append(clip);continue
  shared=['-frames:v',str(shot['frames']),'-an','-c:v','libx264','-preset','veryfast','-crf','23','-pix_fmt','yuv420p','-r','24','-threads',str(threads),'-movflags','+faststart',clip]
  if shot['type']=='video':
   overlay=folder/f'{shot["index"]:03}-overlay.png';layout.header(scene,shot,True).save(overlay)
   selected=timeline['assets'][shot['asset']]
   graph=f'[0:v]fps=24,scale=856:818:force_original_aspect_ratio=decrease,pad=856:818:(ow-iw)/2:(oh-ih)/2:color={layout.bg},setsar=1,pad=1080:1920:56:462:color={layout.bg}[base];[base][1:v]overlay=0:0,format=yuv420p[v]'
   run([ff,'-hide_banner','-loglevel','error','-y','-ss',str(shot['source_start']),'-i',selected['path'],'-loop','1','-i',overlay,'-filter_complex_threads','1','-filter_complex',graph,'-map','[v]']+shared)
  elif shot['type']=='diagram':
   p=subprocess.Popen([ff,'-hide_banner','-loglevel','error','-y','-f','rawvideo','-pix_fmt','rgb24','-s','1080x1920','-r','24','-i','-']+shared,stdin=subprocess.PIPE,stderr=subprocess.PIPE)
   try:
    for frame in range(shot['frames']):p.stdin.write(draw_frame(ctx,scene,shot,frame/FPS).tobytes())
    p.stdin.close();error=p.stderr.read().decode('utf-8','replace');code=p.wait()
    if code:raise RuntimeError(error)
   except Exception:
    p.kill();p.wait();raise
  else:
   image=folder/f'{shot["index"]:03}-still.png';draw_frame(ctx,scene,shot).save(image)
   run([ff,'-hide_banner','-loglevel','error','-y','-loop','1','-framerate','24','-i',image]+shared)
  save(receipt,dict(cache_key=key,sha256=sha(clip),frames=shot['frames']));clips.append(clip)
  print(f'RENDER {edition} {shot["index"]+1}/{len(timeline["shots"])}',flush=True)
 # A ffconcat list uses literal paths, not shell interpolation.
 listing=build/'clips.ffconcat';listing.write_text('ffconcat version 1.0\n'+''.join("file '"+str(p.resolve()).replace('\\','/').replace("'","'\\''")+"'\n" for p in clips),'utf-8')
 concat=build/'visual.mp4';run([ff,'-hide_banner','-loglevel','error','-y','-f','concat','-safe','0','-i',listing,'-c','copy','-an',concat])
 out=ctx['output']/'delivery';out.mkdir(parents=True,exist_ok=True);hq=out/f'{edition}-1080p.mp4'
 subtitles=f"ass=filename='{filter_path(build/'subtitles.ass')}':fontsdir='{filter_path(build/'fonts')}'"
 run([ff,'-hide_banner','-loglevel','error','-y','-i',concat,'-i',build/'mixed.wav','-vf',subtitles,'-map','0:v:0','-map','1:a:0','-frames:v',str(round(timeline['duration']*FPS)),'-c:v','libx264','-preset','veryfast','-crf','23','-pix_fmt','yuv420p','-r','24','-threads',str(threads),'-c:a','aac','-profile:a','aac_low','-b:a','128k','-ac','2','-ar','48000','-t',str(timeline['duration']),'-movflags','+faststart',hq])
 play=out/f'{edition}-play.mp4'
 if hq.stat().st_size<14_900_000:
  # A bitrate budget is a ceiling, not a target to inflate a compressible film.
  run([ff,'-hide_banner','-loglevel','error','-y','-i',hq,'-vf','scale=720:1280:flags=lanczos',
       '-c:v','libx264','-preset','fast','-crf','22','-pix_fmt','yuv420p','-r','24','-threads',str(threads),
       '-c:a','aac','-profile:a','aac_low','-b:a','96k','-ac','2','-ar','48000','-movflags','+faststart',play])
  if play.stat().st_size<15_000_000:
   print('ENCODED',hq,play,flush=True)
   return
 budget=14_500_000;audio_bitrate=96000
 bitrate=min(4_000_000,max(90000,math.floor(budget*8/timeline['duration']-audio_bitrate-20000)))
 stats=build/'play-pass'
 params=['-vf','scale=720:1280:flags=lanczos','-c:v','libx264','-preset','fast','-b:v',str(bitrate),'-pix_fmt','yuv420p','-r','24','-threads',str(threads),'-passlogfile',stats]
 run([ff,'-hide_banner','-loglevel','error','-y','-i',hq]+params+['-pass','1','-an','-f','mp4',os.devnull])
 run([ff,'-hide_banner','-loglevel','error','-y','-i',hq]+params+['-pass','2','-c:a','aac','-profile:a','aac_low','-b:a','96k','-ac','2','-ar','48000','-movflags','+faststart',play])
 if play.stat().st_size>=15_000_000:raise ValueError('Playback file exceeds strict 15MB target; lower the bitrate or use a shorter edition.')
 print('ENCODED',hq,play,flush=True)

def correlation(reference,decoded,lag,step=48):
 # Sparse Pearson correlation uses real decoded samples. Silence is excluded
 # only in window checks; this function never claims transcript recognition.
 a0=max(0,-lag);b0=max(0,lag);length=min(len(reference)-a0,len(decoded)-b0)
 if length<step*10:return None
 n=0;sa=sb=saa=sbb=sab=0.0
 for j in range(0,length,step):
  a=reference[a0+j];b=decoded[b0+j];n+=1;sa+=a;sb+=b;saa+=a*a;sbb+=b*b;sab+=a*b
 denominator=(saa-sa*sa/n)*(sbb-sb*sb/n)
 return (sab-sa*sb/n)/math.sqrt(denominator) if denominator>0 else None

def verify_audio(ctx,media,reference_path,build,stem,timeline):
 # One complete AAC decode yields both PCM and the actual frame timestamp log.
 decoded_path=build/(stem+'-decoded.wav')
 p=run([ctx['ffmpeg'],'-hide_banner','-loglevel','info','-xerror','-err_detect','explode','-y','-i',media,'-vn','-af','ashowinfo','-ac','1','-ar',str(RATE),'-c:a','pcm_s16le',decoded_path])
 reference=read_pcm(reference_path);voice=read_pcm(build/'voice.wav');decoded=read_pcm(decoded_path)
 if len(reference)!=len(voice):raise ValueError('Voice and mixed PCM have different sample counts')
 length_error=(len(decoded)-len(reference))/RATE
 if abs(length_error)>.065:raise ValueError(f'Decoded AAC duration differs by {length_error:.4f}s')
 # Include zero exactly: a shifted coarse grid can select a false periodic peak.
 candidates=[(correlation(reference,decoded,lag),lag) for lag in range(-2400,2401,48)]
 candidates=[x for x in candidates if x[0] is not None]
 if not candidates:raise ValueError('Reference audio has no measurable signal; true audio correlation is unverified')
 _,coarse=max(candidates);fine=[]
 for j in range(coarse-48,coarse+49):
  value=correlation(reference,decoded,j)
  if value is not None:fine.append((value,j))
 best,lag=max(fine)
 if abs(lag)>round(.03*RATE):raise ValueError(f'AAC alignment exceeds 30ms: {lag/RATE:.4f}s')
 if best<.97:raise ValueError(f'Overall AAC/mixed-source correlation too low: {best}')
 windows=[];length=min(len(reference),len(decoded)-lag) if lag>=0 else min(len(reference)+lag,len(decoded))
 def check_window(start,end,scene,kind):
  start=max(start,0,-lag);end=min(end,len(reference),len(decoded)-lag)
  if end-start<RATE//5:return
  a=reference[start:end];v=voice[start:end];b=decoded[start+lag:end+lag]
  sparse=v[::48];rms=math.sqrt(sum(x*x for x in sparse)/max(1,len(sparse)))
  if rms<80:
   if kind=='scene_control':raise ValueError(f'No reference voice signal in scene {scene} control window')
   return
  mixed_correlation=correlation(a,b,0);voice_correlation=correlation(v,b,0)
  if mixed_correlation is None or mixed_correlation<.97:raise ValueError(f'AAC/mixed correlation fails in scene {scene}, {start/RATE:.2f}s: {mixed_correlation}')
  if voice_correlation is None or voice_correlation<.85:raise ValueError(f'AAC/voice correlation fails in scene {scene}, {start/RATE:.2f}s: {voice_correlation}')
  windows.append(dict(scene=scene,kind=kind,start_seconds=start/RATE,duration=(end-start)/RATE,
                      mixed_correlation=round(mixed_correlation,6),voice_correlation=round(voice_correlation,6),reference_voice_rms=round(rms,2)))
 for scene in timeline['scenes']:
  relevant=[c for c in timeline['subtitles'] if c['scene']==scene['index']]
  if not relevant:raise ValueError(f'Scene {scene["index"]} has no measured spoken cues')
  a=round(min(c['start'] for c in relevant)*RATE);b=round(max(c['end'] for c in relevant)*RATE)
  window=min(round(2.5*RATE),b-a)
  if window<=0:raise ValueError('Empty spoken range')
  for fraction in (0,.5,1):
   start=a+round((b-a-window)*fraction);check_window(start,start+window,scene['index'],'scene_control')
  for start in range(a,b,round(1.25*RATE)):
   check_window(start,min(start+round(2.5*RATE),b),scene['index'],'rolling')
 frames=[]
 for line in p.stderr.splitlines():
  m=re.search(r'pts:(-?\d+).*?rate:(\d+).*?nb_samples:(\d+)',line)
  if m:frames.append(tuple(int(x) for x in m.groups()))
 if not frames:raise ValueError('AAC frame timestamps were not observed')
 if frames[0][0]!=0:raise ValueError('AAC decoded timestamps do not begin at zero')
 gaps=[]
 for first,second in zip(frames,frames[1:]):
  if first[1]!=RATE or second[0]-first[0]!=first[2]:gaps.append([first,second])
 if gaps:raise ValueError(f'AAC timestamp discontinuities: {gaps[:3]}')
 return dict(complete_decode=True,decoded_sample_count=len(decoded),sample_error_seconds=length_error,
             correlation=round(best,6),alignment_samples=lag,windows=windows,aac_frames=len(frames),
             aac_pts_continuous=True,dual_reference=['mixed.wav','voice.wav'],mixed_minimum=.97,voice_minimum=.85,
             max_alignment_seconds=.03,not_asr=True)

def verify_video_decode(ctx,media,expected_frames):
 p=run([ctx['ffmpeg'],'-hide_banner','-loglevel','info','-xerror','-err_detect','explode','-i',media,'-map','0:v:0','-an','-vf','showinfo','-f','null','-'])
 base=re.search(r'config in time_base:\s*(\d+)/(\d+)',p.stderr)
 if not base:raise ValueError('Actual decoded video time base was not observed')
 time_base=Fraction(int(base[1]),int(base[2]));frames=[]
 for line in p.stderr.splitlines():
  m=re.search(r'\bn:\s*(\d+)\s+pts:\s*(-?\d+)',line)
  if m:frames.append((int(m[1]),int(m[2])))
 if len(frames)!=expected_frames:raise ValueError(f'Decoded frame count differs: {len(frames)}/{expected_frames}')
 for i,(n,pts) in enumerate(frames):
  if n!=i or pts*time_base!=Fraction(i,FPS):raise ValueError(f'Non-CFR decoded video timestamp at frame {i}: {pts}*{time_base}')
 return dict(complete_video_decode=True,decoded_frames=len(frames),time_base=str(time_base),every_pts_equals_frame_index_over_24=True)

def verify(ctx,edition):
 build=edition_dir(ctx,edition);out=ctx['output']/'delivery';timeline=load_timeline(ctx,edition);layout=Layout(ctx)
 report=dict(schema='portable-documentary-verification-1',edition=edition,status='pending',
             automatic_scope=['encoding geometry/codecs','complete video/audio decode','subtitle timing/typography','source bindings and decoded audio correlation'],
             human_visual_review='pending',human_fact_review='pending',external_license_review='pending',checks={},errors=[])
 try:
  if sha(ctx['path'])!=timeline['project_sha256']:raise ValueError('Project changed after prepare')
  if sha(__file__)!=timeline.get('runtime_script_sha256'):raise ValueError('Renderer changed after prepare')
  if sha(build/'voice.wav')!=timeline['voice_sha256'] or sha(build/'mixed.wav')!=timeline['mix']['mixed_sha256']:raise ValueError('Audio hash binding changed')
  for identifier,item in timeline['assets'].items():
   if sha(item['path'])!=item['sha256']:raise ValueError(f'Source changed: {identifier}')
  report['checks']['input_bindings']=dict(passed=True,project_sha256=timeline['project_sha256'],voice_sha256=timeline['voice_sha256'],mixed_sha256=timeline['mix']['mixed_sha256'],asset_count=len(timeline['assets']),license_declarations_only=True)
  previous=0
  for cue in timeline['subtitles']:
   if not 0<=cue['start']<cue['end']<=timeline['duration'] or cue['start']<previous-.001:raise ValueError('Subtitle timing invalid')
   previous=cue['end'];layout.rows(cue['text'],layout.cn_size,max_rows=2);layout.rows(cue.get('english',''),layout.en_size,english=True,max_rows=2)
  blocks=(out/f'{edition}-bilingual.srt').read_text('utf-8-sig').strip().split('\n\n')
  if len(blocks)!=len(timeline['subtitles']):raise ValueError('SRT cue count differs')
  for i,(block,c) in enumerate(zip(blocks,timeline['subtitles']),1):
   rows=block.splitlines();expected=layout.rows(c.get('english',''),layout.en_size,english=True,max_rows=2)
   if rows[0]!=str(i) or rows[1]!=f'{timestamp(c["start"])} --> {timestamp(c["end"])}' or rows[2:]!=[c['text']]+expected:raise ValueError('SRT content/timing differs from timeline')
  english_count=sum(bool(c.get('english','').strip()) for c in timeline['subtitles'])
  report['checks']['subtitles']=dict(passed=True,cues=len(blocks),timing_source=timeline['provenance']['method'],
                                   english_cue_count=english_count,english_under_chinese=bool(blocks) and english_count==len(blocks),max_cn_lines=2,max_en_lines=2)
  report['checks']['media']={};report['checks']['audio']={}
  for suffix,size in [('1080p',(1080,1920)),('play',(720,1280))]:
   media=out/f'{edition}-{suffix}.mp4';metadata=probe(ctx['ffmpeg'],media)
   if (metadata['width'],metadata['height'])!=size or metadata['fps']!=24:raise ValueError(f'Wrong geometry/frame rate: {media}')
   if 'h264' not in metadata['video'] or 'yuv420p' not in metadata['video']:raise ValueError('Expected H264 yuv420p')
   if 'aac' not in metadata['audio'] or '48000 Hz' not in metadata['audio'] or 'stereo' not in metadata['audio']:raise ValueError('Expected 48kHz stereo AAC')
   if abs(metadata['duration']-timeline['duration'])>.08:raise ValueError('Media duration differs from timeline')
   if suffix=='play' and media.stat().st_size>=15_000_000:raise ValueError('Playback MP4 exceeds 15MB')
   if not faststart(media):raise ValueError('MP4 moov must precede mdat')
   decoded=verify_video_decode(ctx,media,round(timeline['duration']*FPS))
   report['checks']['media'][suffix]=dict(passed=True,path=str(media),sha256=sha(media),bytes=media.stat().st_size,width=size[0],height=size[1],duration=metadata['duration'],fps=24,codec='H264 yuv420p / AAC 48k stereo',faststart=True,**decoded)
   report['checks']['audio'][suffix]=verify_audio(ctx,media,build/'mixed.wav',build,suffix,timeline)
  report['status']='automatic_checks_passed'
 except Exception as exc:
  report['status']='failed';report['errors'].append(str(exc))
 save(out/f'{edition}-verification.json',report)
 print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)
 if report['status']=='failed':raise RuntimeError('Automatic verification failed; see delivery report')
 return report

def doctor(ffmpeg=None):
 result=dict(python=sys.executable,python_version=sys.version.split()[0],ffmpeg=None,PIL=False,edge_tts=False,ass_filter=False)
 for name in ('PIL','edge_tts'):result[name]=importlib.util.find_spec(name) is not None
 try:
  result['ffmpeg']=find_ffmpeg(ffmpeg)
  filters=run([result['ffmpeg'],'-hide_banner','-filters']).stdout
  result['ass_filter']=bool(re.search(r'\bass\s',filters))
  result['font']=str(font_path())
 except Exception as exc:result['error']=str(exc)
 print(json.dumps(result,ensure_ascii=False,indent=2))
 if not result['PIL'] or not result['ffmpeg'] or not result['ass_filter']:raise RuntimeError('Required runtime capability missing')

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('command',choices=['doctor','build-voice','prepare','preview','render','verify','build'])
 parser.add_argument('--project',type=Path);parser.add_argument('--edition',choices=['short','full'],default='short')
 parser.add_argument('--ffmpeg');parser.add_argument('--python',dest='python_path');parser.add_argument('--vendor',action='append',default=[])
 parser.add_argument('--threads',type=int,default=3);args=parser.parse_args()
 if args.python_path and Path(args.python_path).resolve()!=Path(sys.executable).resolve():
  argv=sys.argv[1:];position=argv.index('--python');del argv[position:position+2]
  raise SystemExit(subprocess.call([args.python_path,__file__,*argv]))
 for folder in args.vendor:sys.path.insert(0,str(Path(folder).expanduser().resolve()))
 if args.command=='doctor':doctor(args.ffmpeg);return
 if not args.project:parser.error('--project is required')
 ctx=context(args.project,args.ffmpeg)
 if args.edition not in ctx['project']['editions']:raise ValueError('Requested edition is not configured')
 if args.command=='build':
  build_voice(ctx,args.edition);prepare(ctx,args.edition);preview(ctx,args.edition);render(ctx,args.edition,args.threads);verify(ctx,args.edition)
 elif args.command=='build-voice':build_voice(ctx,args.edition)
 elif args.command=='prepare':prepare(ctx,args.edition)
 elif args.command=='preview':preview(ctx,args.edition)
 elif args.command=='render':render(ctx,args.edition,args.threads)
 elif args.command=='verify':verify(ctx,args.edition)

if __name__=='__main__':main()
