import {DEMO_BRANCHES, DEMO_HAND, percent} from './math/card-removal';

export const CONTENT = {
  eyebrow: '明牌抽取实验',
  disclaimer: '教学模型 · 非实际牌局规则',
  question: ['只剩两张牌，', '下一张会抽到谁？'],
  current: '当前剩牌',
  rule: '从当前剩牌中，等概率抽走一张。',
  firstCaption: [`只剩 ${DEMO_HAND.join(' 和 ')}，`, '每次等概率抽走一张。'],
  probabilityCaption: [
    `下一步抽到 ${DEMO_BRANCHES[0].draw} 或 ${DEMO_BRANCHES[1].draw}，`,
    DEMO_BRANCHES.every(branch => branch.probability === DEMO_BRANCHES[0].probability)
      ? `概率各占 ${percent(DEMO_BRANCHES[0].probability)}。`
      : `概率分别为 ${DEMO_BRANCHES.map(branch => percent(branch.probability)).join(' 和 ')}。`,
  ],
  conclusionCaption: ['抽走一张以后，', '留下的牌就是新的状态。'],
  remaining: '下一状态：剩',
};
