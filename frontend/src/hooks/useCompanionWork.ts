import { useEffect, useLayoutEffect, useRef, useState } from "react";
import {
  laptopOpeningMs,
  laptopPackingMs,
} from "../components/companion-laptop";

export type CompanionWorkPhase = "idle" | "opening" | "working" | "packing";

// Keep the short setup/put-away sequences independent of canvas redraws and focus.
export function useCompanionWork(busy: boolean, animated: boolean) {
  const [phase, setPhase] = useState<CompanionWorkPhase>("idle");
  const started = useRef(0);

  let next = phase;
  if (busy && (next === "idle" || next === "packing"))
    next = animated ? "opening" : "working";
  else if (!busy && next === "working") next = animated ? "packing" : "idle";
  if (!animated) {
    if (next === "opening") next = busy ? "working" : "idle";
    if (next === "packing") next = "idle";
  }
  if (next !== phase) setPhase(next);

  useLayoutEffect(() => {
    started.current = performance.now();
  }, [phase]);

  useEffect(() => {
    if (!animated || (phase !== "opening" && phase !== "packing")) return;
    const duration = phase === "opening" ? laptopOpeningMs : laptopPackingMs;
    const timer = window.setTimeout(
      () => {
        setPhase(phase === "opening" ? (busy ? "working" : "packing") : "idle");
      },
      Math.max(0, duration - (performance.now() - started.current)),
    );
    return () => window.clearTimeout(timer);
  }, [busy, animated, phase]);

  return {
    phase,
    started,
    dismiss: () => {
      if (!busy) setPhase("idle");
    },
  };
}
