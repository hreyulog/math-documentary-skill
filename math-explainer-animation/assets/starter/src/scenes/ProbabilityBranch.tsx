import React from 'react';
import {useCurrentFrame, useVideoConfig} from 'remotion';
import {Card} from '../components/Card';
import {CONTENT} from '../content';
import {STYLE as S} from '../config/style';
import {ease, TIMELINE as T} from '../config/timeline';
import {DEMO_BRANCHES, DEMO_HAND, percent} from '../math/card-removal';

export const ProbabilityBranch: React.FC = () => {
  const frame = useCurrentFrame();
  const {width, height} = useVideoConfig();
  const portrait = height > width;
  const center = width / 2;
  const headingY = portrait ? 140 : 95;
  const questionY = portrait ? 315 : 190;
  const currentY = portrait ? 655 : 390;
  const branchStartY = portrait ? 820 : 510;
  const panelY = portrait ? 1100 : 665;
  const panelW = portrait ? 430 : 590;
  const panelH = portrait ? 380 : 230;
  const destinations = portrait ? [295, 785] : [570, 1350];
  const cardSize = portrait ? 125 : 100;
  const stateProgress = ease(frame, ...T.stateArrives);
  const branchesProgress = ease(frame, ...T.branchesDraw);
  const outcomeProgress = ease(frame, ...T.outcomesArrive);
  const probabilityProgress = ease(frame, ...T.probabilitiesArrive);
  const caption = frame >= T.conclusion ? CONTENT.conclusionCaption
    : frame >= T.probabilitiesArrive[0] ? CONTENT.probabilityCaption : CONTENT.firstCaption;

  return <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} style={{fontFamily:S.font}}>
    <defs>
      <radialGradient id="table-light"><stop stopColor="#30464d"/><stop offset="1" stopColor={S.background}/></radialGradient>
    </defs>
    <rect width={width} height={height} fill={S.background}/>
    <ellipse cx={center} cy={currentY} rx={width * .62} ry={portrait ? 570 : 350} fill="url(#table-light)" opacity={.7}/>
    <text x={84} y={headingY} fontSize={portrait ? 39 : 35} fill={S.first} fontWeight={700}>{CONTENT.eyebrow}</text>
    <text x={84} y={headingY + 61} fontSize={portrait ? 31 : 27} fill={S.muted}>{CONTENT.disclaimer}</text>
    {CONTENT.question.map((line, i) => <text key={line} x={center} y={questionY + i * (portrait ? 70 : 57)} textAnchor="middle" fontSize={portrait ? 57 : 47} fill={S.text} fontWeight={700}>{line}</text>)}

    <g opacity={stateProgress} transform={`translate(0 ${(1 - stateProgress) * 55})`}>
      <text x={center} y={currentY - (portrait ? 153 : 100)} textAnchor="middle" fontSize={portrait ? 36 : 29} fill={S.muted}>{CONTENT.current}</text>
      {DEMO_HAND.map((rank, i) => <Card key={rank} rank={rank} x={center + (i - .5) * (cardSize + 27)} y={currentY} width={cardSize}/>)}
    </g>
    <text x={center} y={currentY + (portrait ? 137 : 105)} textAnchor="middle" fill={S.muted} fontSize={portrait ? 31 : 26}>{CONTENT.rule}</text>

    {DEMO_BRANCHES.map((branch, i) => {
      const x = destinations[i];
      const color = i === 0 ? S.first : S.second;
      const path = `M ${center} ${branchStartY} C ${center} ${branchStartY + 80}, ${x} ${panelY - 100}, ${x} ${panelY - 24}`;
      return <g key={branch.draw}>
        <path d={path} stroke={S.line} strokeWidth={5} fill="none" opacity={.22}/>
        <path d={path} stroke={color} strokeWidth={6} fill="none" pathLength={1} strokeDasharray="1" strokeDashoffset={1 - branchesProgress} opacity={branchesProgress}/>
        <path d={`M ${x - 12} ${panelY - 43} L ${x} ${panelY - 24} L ${x + 12} ${panelY - 43}`} stroke={color} strokeWidth={5} fill="none" opacity={branchesProgress}/>
        <g opacity={outcomeProgress} transform={`translate(0 ${(1 - outcomeProgress) * 35})`}>
          <rect x={x - panelW / 2} y={panelY} width={panelW} height={panelH} rx={25} fill={S.panel} stroke={color} strokeWidth={2}/>
          <text x={x} y={panelY + (portrait ? 65 : 52)} textAnchor="middle" fill={S.text} fontSize={portrait ? 36 : 30}>抽走 {branch.draw}</text>
          <g opacity={probabilityProgress}>
            <text x={x} y={panelY + (portrait ? 144 : 109)} textAnchor="middle" fill={color} fontSize={portrait ? 65 : 49} fontWeight={700}>{percent(branch.probability)}</text>
            <rect x={x - panelW * .34} y={panelY + (portrait ? 172 : 126)} width={panelW * .68} height={11} rx={5} fill={S.line} opacity={.35}/>
            <rect x={x - panelW * .34} y={panelY + (portrait ? 172 : 126)} width={panelW * .68 * branch.probability} height={11} rx={5} fill={color}/>
          </g>
          <text x={x - (portrait ? 65 : 44)} y={panelY + (portrait ? 295 : 190)} textAnchor="middle" fill={S.muted} fontSize={portrait ? 32 : 27}>{CONTENT.remaining}</text>
          <Card rank={branch.next[0]} x={x + (portrait ? 105 : 135)} y={panelY + (portrait ? 282 : 182)} width={portrait ? 70 : 54}/>
        </g>
      </g>;
    })}
    <g>
      <rect x={64} y={portrait ? 1610 : 938} width={width - 128} height={portrait ? 215 : 110} rx={20} fill="#0c1419"/>
      {caption.map((line, i) => <text key={line} x={center} y={(portrait ? 1690 : 979) + i * (portrait ? 65 : 43)} textAnchor="middle" fontSize={portrait ? 44 : 34} fill={S.text}>{line}</text>)}
    </g>
  </svg>;
};
