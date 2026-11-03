import type { ListingStatus } from "./types";

export interface AssistantStatus {
  available: boolean;
  message: string;
}
export interface AssistantListing {
  id: string;
  title: string;
  city: string;
  kind: string;
  unit_name: string;
  monthly_rent: string;
  available_now: boolean;
  status?: ListingStatus | null;
  available_from?: string | null;
  available_until?: string | null;
}
export interface AssistantAction {
  id: string;
  kind: string;
  summary: string;
  payload: Record<string, string | number | boolean | string[] | null>;
  status: "pending" | "confirmed" | "cancelled";
  expires_at: string;
  result: { id?: string } | null;
}
export interface AssistantMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  listings: AssistantListing[];
  actions: AssistantAction[];
  created_at: string;
}
export interface AssistantThread {
  id: string;
  title: string;
  updated_at: string;
}
export interface AssistantThreadDetail extends AssistantThread {
  messages: AssistantMessage[];
}
