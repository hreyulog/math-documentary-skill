import React from 'react';
import {Composition} from 'remotion';
import config from './config/series.json';
import {TIMELINE} from './config/timeline';
import {Preview} from './Preview';

export const RemotionRoot: React.FC = () => <Composition id="MathPreview" component={Preview}
  durationInFrames={TIMELINE.durationInFrames} fps={TIMELINE.fps}
  width={config.layout === 'landscape' ? 1920 : 1080}
  height={config.layout === 'landscape' ? 1080 : 1920}/>;
