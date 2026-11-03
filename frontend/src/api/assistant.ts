import type { ListingStatus, VisitStatus } from "./types";

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
export interface AssistantListingSearch {
  page: number;
  page_size: number;
  total: number;
  cards_only: boolean;
}
export interface AssistantListingPage {
  items: AssistantListing[];
  page: number;
  page_size: number;
  total: number;
}
export interface AssistantListingSearchContext {
  message_id: string;
  page: number;
}
export interface AssistantVisit {
  id: string;
  property_title: string;
  unit_name: string;
  tenant_name: string;
  status: VisitStatus;
  requested_at: string;
  scheduled_at: string | null;
  duration_minutes: number;
  note: string | null;
}
export interface AssistantVisitPage {
  items: AssistantVisit[];
  page: number;
  page_size: number;
  total: number;
}
export interface AssistantVisitSearch extends AssistantVisitPage {
  cards_only: boolean;
}
export interface AssistantVisitSearchContext {
  message_id: string;
  page: number;
}
export interface AssistantMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  listings: AssistantListing[];
  listing_search?: AssistantListingSearch | null;
  visit_search?: AssistantVisitSearch | null;
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
