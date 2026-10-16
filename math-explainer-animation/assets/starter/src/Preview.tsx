import React from 'react';
import {AbsoluteFill, Audio, interpolate, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import config from './config/series.json';
import {STYLE} from './config/style';
import {ProbabilityBranch} from './scenes/ProbabilityBranch';

export const Preview: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps, durationInFrames} = useVideoConfig();
  const volume = interpolate(frame, [0, 12, durationInFrames - 30, durationInFrames - 1], [0, config.music.gain, config.music.gain, 0], {extrapolateLeft:'clamp', extrapolateRight:'clamp'});
  return <AbsoluteFill style={{backgroundColor: STYLE.background}}>
    <ProbabilityBranch/>
    {config.accountName && <div style={{position:'absolute', right:84, top:55, fontFamily:STYLE.font, color:STYLE.muted, fontSize:25}}>{config.accountName}</div>}
    {config.music.path && <Audio src={staticFile(config.music.path)} trimBefore={Math.round(config.music.offsetSeconds * fps)} volume={volume}/>}
  </AbsoluteFill>;
};
