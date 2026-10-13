"""Small, portable helpers shared by the documentary runtime."""
from __future__ import annotations
import array, hashlib, json, os, re, shutil, struct, subprocess, sys, wave
from pathlib import Path

RATE=48000
FPS=24

def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for block in iter(lambda:f.read(1048576),b''):h.update(block)
 return h.hexdigest()

def fingerprint(value):
 return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def save(path,value):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
 path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n','utf-8')

def run(args):
 p=subprocess.run([str(x) for x in args],capture_output=True,text=True,encoding='utf-8',errors='replace')
 if p.returncode:raise RuntimeError(f'Command failed ({p.returncode}): {args[0]}\n{p.stderr[-7000:]}')
 return p

def find_ffmpeg(explicit=None):
 if explicit:
  p=Path(explicit).expanduser().resolve()
  if not p.is_file():raise FileNotFoundError(p)
  return str(p)
 if os.environ.get('VIDEO_FFMPEG'):return find_ffmpeg(os.environ['VIDEO_FFMPEG'])
 found=shutil.which('ffmpeg')
 if found:return found
 try:
  import imageio_ffmpeg
  return imageio_ffmpeg.get_ffmpeg_exe()
 except ImportError:pass
 for folder in (Path(__file__).parent/'vendor',Path(__file__).parents[1]/'vendor'):
  found=next(folder.glob('**/ffmpeg*exe'),None) if folder.exists() else None
  if found:return str(found)
 raise RuntimeError('FFmpeg not found. Pass --ffmpeg, set VIDEO_FFMPEG, or provide imageio_ffmpeg / PATH ffmpeg.')

def resolve(base,value):
 p=Path(value).expanduser()
 return p.resolve() if p.is_absolute() else (Path(base)/p).resolve()

def probe(ffmpeg,path):
 p=subprocess.run([ffmpeg,'-hide_banner','-i',str(path)],capture_output=True,text=True,encoding='utf-8',errors='replace')
 info=p.stderr
 duration=re.search(r'Duration:\s*(\d+):(\d+):([\d.]+)',info)
 video=next((x for x in info.splitlines() if 'Video:' in x),'')
 audio=next((x for x in info.splitlines() if 'Audio:' in x),'')
 size=re.search(r'\b(\d{2,5})x(\d{2,5})\b',video)
 fps=re.search(r'([\d.]+) fps',video)
 return dict(duration=(int(duration[1])*3600+int(duration[2])*60+float(duration[3])) if duration else None,
             width=int(size[1]) if size else None,height=int(size[2]) if size else None,
             fps=float(fps[1]) if fps else None,video=video,audio=audio,raw=info)

def read_pcm(path):
 with wave.open(str(path),'rb') as f:
  if (f.getframerate(),f.getnchannels(),f.getsampwidth())!=(RATE,1,2):
   raise ValueError(f'Canonical PCM must be {RATE}Hz mono int16: {path}')
  samples=array.array('h',f.readframes(f.getnframes()))
 if sys.byteorder!='little':samples.byteswap()
 return samples

def write_pcm(path,samples):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
 copy=array.array('h',samples)
 if sys.byteorder!='little':copy.byteswap()
 with wave.open(str(path),'wb') as f:
  f.setnchannels(1);f.setsampwidth(2);f.setframerate(RATE);f.writeframes(copy.tobytes())

def canonical_pcm(ffmpeg,source,target,filters=None):
 args=[ffmpeg,'-hide_banner','-loglevel','error','-y','-i',source,'-vn']
 if filters:args+=['-af',filters]
 run(args+['-ac','1','-ar',str(RATE),'-c:a','pcm_s16le',target])
 return len(read_pcm(target))/RATE

def faststart(path):
 atoms=[];size=Path(path).stat().st_size
 with Path(path).open('rb') as f:
  offset=0
  while offset+8<=size:
   f.seek(offset);head=f.read(8);length,name=struct.unpack('>I4s',head)
   if length==1:length=struct.unpack('>Q',f.read(8))[0]
   if length==0:length=size-offset
   if length<8:break
   atoms.append(name.decode('ascii','replace'));offset+=length
 return 'moov' in atoms and 'mdat' in atoms and atoms.index('moov')<atoms.index('mdat')

def timestamp(seconds):
 milliseconds=round(seconds*1000);hours,milliseconds=divmod(milliseconds,3600000)
 minutes,milliseconds=divmod(milliseconds,60000);seconds,milliseconds=divmod(milliseconds,1000)
 return f'{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}'
