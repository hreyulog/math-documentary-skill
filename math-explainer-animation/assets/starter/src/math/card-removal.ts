export const CARD_ORDER = ['A', 'Q', 'K', '3'] as const;
export type Card = (typeof CARD_ORDER)[number];
export type Hand = readonly Card[];

export const canonical = (hand: Hand): Card[] => {
  if (new Set(hand).size !== hand.length || hand.some(c => !CARD_ORDER.includes(c))) {
    throw new Error('A state must be a subset of A, Q, K, 3 without duplicate cards.');
  }
  return CARD_ORDER.filter(c => hand.includes(c));
};

export const removeCard = (hand: Hand, card: Card): Card[] => {
  const valid = canonical(hand);
  if (!valid.includes(card)) throw new Error(`Cannot remove absent card ${card}`);
  return valid.filter(c => c !== card);
};

export const remainingAfter = (history: readonly Card[], initial: Hand = CARD_ORDER): Card[] =>
  history.reduce<Card[]>((hand, card) => removeCard(hand, card), canonical(initial));

export const nextDraws = (hand: Hand) => {
  const current = canonical(hand);
  return current.map(draw => ({draw, probability: 1 / current.length, next: removeCard(current, draw)}));
};

// The empty state is absorbing; it has no next draw but one state transition.
export const transitions = (hand: Hand) => {
  const current = canonical(hand);
  return current.length ? nextDraws(current).map(({next, probability}) => ({next, probability}))
    : [{next: [] as Card[], probability: 1}];
};

export const DEMO_HAND = remainingAfter(['A', 'Q']);
export const DEMO_BRANCHES = nextDraws(DEMO_HAND);
export const percent = (probability: number) => `${Math.round(probability * 100)}%`;
