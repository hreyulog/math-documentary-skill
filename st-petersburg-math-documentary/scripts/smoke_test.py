"""Actual offline codec test, using synthetic media and a non-speech tone.

Does not call TTS, does not represent a human/factual review, and does not
claim that the tone matches a narration transcript. Temporary data is removed
unless --keep is passed. This test exercises every supported shot type.
"""
from __future__ import annotations
import argparse,array,json,math,sys,tempfile
sys.dont_write_bytecode=True
from pathlib import Path
from runtime_support import RATE,find_ffmpeg,run,save,write_pcm

def test(folder,ffmpeg):
 from PIL import Image,ImageDraw
 import video_runtime as v
 folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
 im=Image.new('RGB',(640,360),'#263b40');d=ImageDraw.Draw(im)
 d.rectangle((90,70,550,290),outline='#e5bd7f',width=9);im.save(folder/'fixture.png')
 run([ffmpeg,'-hide_banner','-loglevel','error','-y','-f','lavfi','-i','testsrc2=size=640x360:rate=24:duration=3','-an','-c:v','libx264','-pix_fmt','yuv420p',folder/'fixture.mp4'])
 samples=array.array('h',(round(4700*math.sin(2*math.pi*220*i/RATE+6*math.sin(2*math.pi*.8*i/RATE))+1300*math.sin(2*math.pi*613*i/RATE)) for i in range(RATE*4)))
 write_pcm(folder/'tone.wav',samples)
 subtitles=[dict(start=.25,end=3.65,scene=0,text='这是合成素材的编码自检。',english='Synthetic media and a tone; not narration.')]
 save(folder/'cues.json',subtitles)
 project=dict(schema='portable-documentary-project-1',title='离线编码自检',person=dict(name='Synthetic fixture'),output_dir='output',
              assets={
               'picture':dict(type='image',path='fixture.png',credit='smoke_test.py',license='Original synthetic test fixture',caption_label='合成测试图 · 非历史图片'),
               'motion':dict(type='video',path='fixture.mp4',credit='FFmpeg testsrc2',license='Original synthetic test fixture',caption_label='合成测试画面 · 非真实场景')},
              editions={'short':dict(voice_wav='tone.wav',subtitles='cues.json',scenes=[dict(id='fixture',headline='离线技术自检\n非人物样片',duration=4,shots=[
               dict(type='card',duration=1,title='技术验证',lines=['合成图、视频与音调']),
               dict(type='image',asset='picture',duration=1),
               dict(type='video',asset='motion',source_start=.5,duration=1),
               dict(type='diagram',duration=1,title='两种状态',diagram=dict(kind='transition',states=['A','B'],matrix=[[.8,.2],[.4,.6]]))])])})
 save(folder/'project.json',project);ctx=v.context(folder/'project.json',ffmpeg)
 v.build_voice(ctx,'short');v.prepare(ctx,'short');v.preview(ctx,'short');v.render(ctx,'short',2)
 report=v.verify(ctx,'short')
 assert report['status']=='automatic_checks_passed'
 print('SMOKE PASSED: actual complete MP4 decode, PCM/AAC correlation, AAC continuity, subtitles and geometry. Synthetic audio is not speech.',flush=True)
 return report

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--ffmpeg');parser.add_argument('--vendor',action='append',default=[]);parser.add_argument('--keep',action='store_true')
 args=parser.parse_args()
 for folder in args.vendor:sys.path.insert(0,str(Path(folder).resolve()))
 ffmpeg=find_ffmpeg(args.ffmpeg)
 if args.keep:
  folder=Path(tempfile.mkdtemp(prefix='portable-video-smoke-'));print('SMOKE DATA',folder);test(folder,ffmpeg)
 else:
  with tempfile.TemporaryDirectory(prefix='portable-video-smoke-') as folder:test(folder,ffmpeg)

if __name__=='__main__':main()
