import { createContext, useContext } from "react";
import type { Role } from "../api/types";

export interface DemoStatus {
  enabled: boolean;
  read_only: boolean;
  assistant_mode: "simulated" | "live" | "unavailable";
  roles: Role[];
  loading?: boolean;
}
export const normal: DemoStatus = {
  enabled: false,
  read_only: false,
  assistant_mode: "unavailable",
  roles: [],
};
export const DemoContext = createContext(normal);

export function useDemo() {
  return useContext(DemoContext);
}

export const demoPrompts: Record<Role, string[]> = {
  tenant: [
    "Find rooms in Bologna under €700/month.",
    "Show my applications.",
    "Show my visits.",
    "Explain how the rental workflow works.",
  ],
  landlord: [
    "Show my properties.",
    "Give me an occupancy report.",
    "Show my rental contracts.",
    "Explain how to publish a listing.",
  ],
  admin: [
    "Show listings waiting for approval.",
    "Show pending applications.",
    "Show requested visits.",
    "Give me an occupancy report.",
  ],
};
