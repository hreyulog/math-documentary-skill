// Video-frame indices, not audio-analysis frame indices.
export const TIMELINE = {
  fps: 30,
  durationInFrames: 450,
  stateArrives: [0, 30],
  branchesDraw: [75, 120],
  outcomesArrive: [120, 150],
  probabilitiesArrive: [165, 180],
  conclusion: 300,
} as const;

export const ease = (frame: number, start: number, end: number): number => {
  const t = Math.max(0, Math.min(1, (frame - start) / (end - start)));
  return t * t * (3 - 2 * t);
};
