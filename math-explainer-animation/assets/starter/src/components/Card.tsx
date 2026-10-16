import React from 'react';
import {Card as CardId} from '../math/card-removal';
import {STYLE} from '../config/style';

export const Card: React.FC<{rank: CardId; x: number; y: number; width?: number}> = ({rank, x, y, width = 120}) => {
  const height = width * 1.42;
  return <g transform={`translate(${x - width / 2} ${y - height / 2})`}>
    <rect x={3} y={7} width={width} height={height} rx={14} fill="#000" opacity={0.18}/>
    <rect width={width} height={height} rx={14} fill={STYLE.card}/>
    <text x={width * .16} y={height * .25} fill={STYLE.ink} fontSize={width * .31} fontWeight={700}>{rank}</text>
    <text x={width / 2} y={height * .72} textAnchor="middle" fill={STYLE.ink} fontSize={width * .49}>{rank === '3' ? '♣' : '♠'}</text>
  </g>;
};
