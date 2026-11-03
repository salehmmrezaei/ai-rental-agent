export type LaptopPhase = "opening" | "working" | "packing";

export const laptopOpeningMs = 650;
export const laptopPackingMs = 900;

const ink = "#111e50";
const shell = "#8ba5d2";
const light = "#c4d9f2";
const blue = "#4e8df4";
const cyan = "#91f2ff";

const clamp = (value: number) => Math.max(0, Math.min(1, value));
const ease = (value: number) => 1 - (1 - clamp(value)) ** 3;

/** Draw in the mascot canvas's logical 72 × 80 coordinate space. */
export function drawCompanionLaptop(
  context: CanvasRenderingContext2D,
  phase: LaptopPhase,
  elapsedMs: number,
  animated: boolean,
) {
  const elapsed = Math.max(0, elapsedMs);
  const opening = phase === "opening" ? ease((elapsed - 100) / 450) : 1;
  const closing = phase === "packing" ? ease(elapsed / 330) : 0;
  const tucked = phase === "packing" ? ease((elapsed - 330) / 320) : 0;
  if (tucked >= 1) return;

  context.save();
  context.imageSmoothingEnabled = false;
  context.globalAlpha *=
    (phase === "opening" ? clamp(elapsed / 120) : 1) * (1 - tucked);
  // The closed laptop slips under Blu's right arm before Blu stands up.
  // Keep the lid below Blu's mouth and cheeks, resting in front of its feet.
  context.translate(Math.round(tucked * 15), 2 + Math.round(tucked * -5));
  context.translate(36, 66);
  context.scale(1 - tucked * 0.45, 1 - tucked * 0.45);
  context.translate(-36, -66);

  const rect = (
    x: number,
    y: number,
    width: number,
    height: number,
    color: string,
  ) => {
    context.fillStyle = color;
    context.fillRect(x, y, width, height);
  };

  // A shallow keyboard deck and its tapered, pixel-stepped front edge.
  rect(22, 63, 28, 4, ink);
  rect(20, 65, 32, 2, ink);
  rect(22, 64, 28, 2, light);
  rect(21, 65, 30, 1, shell);
  rect(23, 67, 26, 1, ink);

  const lidHeight = Math.max(2, Math.round(11 * opening * (1 - closing)));
  const top = 65 - lidHeight;
  // The lid's back faces the viewer; its bright mark reads at the tiny scale.
  rect(23, top, 26, lidHeight, ink);
  rect(22, top + 1, 28, Math.max(1, lidHeight - 1), ink);
  if (lidHeight > 3) {
    rect(24, top + 1, 24, lidHeight - 2, shell);
    rect(24, top + 1, 24, 1, light);
    rect(23, top + 2, 1, lidHeight - 3, light);
    rect(47, top + 2, 1, lidHeight - 3, "#647db4");
  }
  if (lidHeight >= 9) {
    const emblemY = top + Math.floor(lidHeight / 2) - 1;
    rect(35, emblemY, 2, 4, cyan);
    rect(34, emblemY + 1, 4, 2, cyan);
  }

  if (phase !== "packing" && opening > 0.65) {
    const beat = animated ? Math.floor(elapsed / 140) % 4 : 0;
    const leftTap = animated && beat === 1 ? 1 : 0;
    const rightTap = animated && beat === 3 ? 1 : 0;
    // Small blue paws wrap around the lid's sides to tap the keyboard.
    rect(19, 60 + leftTap, 5, 4, ink);
    rect(20, 60 + leftTap, 4, 3, blue);
    rect(20, 60 + leftTap, 2, 1, "#86b8ff");
    rect(48, 60 + rightTap, 5, 4, ink);
    rect(48, 60 + rightTap, 4, 3, blue);
    rect(49, 60 + rightTap, 2, 1, "#86b8ff");
    rect(26 + (beat % 2) * 2, 65, 2, 1, cyan);
  }
  context.restore();
}
