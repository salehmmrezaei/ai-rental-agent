export type PetActivity =
  | "idle"
  | "walk-left"
  | "walk-right"
  | "wave"
  | "wink"
  | "sit"
  | "read"
  | "listen"
  | "phone"
  | "jump"
  | "pet";

export const activities: Record<
  PetActivity,
  {
    label: string;
    description: string;
    row:
      | "idle"
      | "walk"
      | "wave"
      | "wink"
      | "sit"
      | "read"
      | "listen"
      | "phone"
      | "jump"
      | "pet";
    frameMs: number;
    duration: number;
  }
> = {
  idle: {
    label: "Stand",
    description: "standing",
    row: "idle",
    frameMs: 340,
    duration: 5500,
  },
  "walk-left": {
    label: "Walk left",
    description: "walking left",
    row: "walk",
    frameMs: 125,
    duration: 5000,
  },
  "walk-right": {
    label: "Walk right",
    description: "walking right",
    row: "walk",
    frameMs: 125,
    duration: 5000,
  },
  wave: {
    label: "Wave",
    description: "waving hello",
    row: "wave",
    frameMs: 200,
    duration: 3600,
  },
  wink: {
    label: "Wink",
    description: "giving you a wink",
    row: "wink",
    frameMs: 250,
    duration: 3000,
  },
  sit: {
    label: "Sit",
    description: "taking a little break",
    row: "sit",
    frameMs: 400,
    duration: 7000,
  },
  read: {
    label: "Read a book",
    description: "reading a book",
    row: "read",
    frameMs: 500,
    duration: 12000,
  },
  listen: {
    label: "Headphones",
    description: "listening to music",
    row: "listen",
    frameMs: 240,
    duration: 10000,
  },
  phone: {
    label: "Use phone",
    description: "checking its phone",
    row: "phone",
    frameMs: 400,
    duration: 9000,
  },
  jump: {
    label: "Jump",
    description: "jumping for joy",
    row: "jump",
    frameMs: 145,
    duration: 2600,
  },
  pet: {
    label: "Pet Blu",
    description: "enjoying a little head pat",
    row: "pet",
    frameMs: 200,
    duration: 2400,
  },
};

export function walkingLimit(viewportWidth: number) {
  // Keep the little walking area in the right-hand half of narrow screens.
  return Math.max(0, Math.min(120, viewportWidth * 0.28, viewportWidth - 100));
}

export function movePet(
  offset: number,
  kind: PetActivity,
  elapsedMs: number,
  limit: number,
) {
  const distance = Math.max(0, Math.min(elapsedMs, 64)) * 0.016;
  let next =
    kind === "walk-left"
      ? offset + distance
      : kind === "walk-right"
        ? offset - distance
        : offset;
  next = Math.max(0, Math.min(limit, next));
  const turned =
    kind === "walk-left" && next >= limit
      ? "walk-right"
      : kind === "walk-right" && next <= 0
        ? "walk-left"
        : kind;
  return { offset: next, kind: turned as PetActivity };
}

export function shuffledActivities(): PetActivity[] {
  const values = (Object.keys(activities) as PetActivity[]).filter(
    (activity) => activity !== "pet",
  );
  for (let i = values.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [values[i], values[j]] = [values[j], values[i]];
  }
  return values;
}
