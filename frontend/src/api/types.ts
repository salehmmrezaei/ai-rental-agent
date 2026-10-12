export type Role = "tenant" | "landlord" | "admin";
export type Kind = "apartment" | "room";
export type ListingStatus =
  "draft" | "submitted" | "approved" | "rejected" | "published" | "unpublished";
export type ApplicationStatus =
  "submitted" | "reviewing" | "approved" | "rejected" | "withdrawn";
export type ContractStatus =
  "confirmed" | "active" | "completed" | "terminated" | "cancelled";
export type VisitStatus =
  "requested" | "scheduled" | "completed" | "cancelled" | "rejected";
export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}
export interface User {
  id: string;
  email: string;
  full_name: string;
  role: Role;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}
export interface TokenResponse {
  access_token: string;
  expires_in: number;
  user: User;
}
export interface PropertyImage {
  id: string;
  property_id: string;
  rental_unit_id: string | null;
  alt_text: string;
  position: number;
  url: string;
}
export interface Listing {
  id: string;
  rental_unit_id: string;
  status: ListingStatus;
  available_from: string;
  available_until: string | null;
  review_note: string | null;
}
export interface Unit {
  id: string;
  property_id: string;
  kind: Kind;
  name: string;
  monthly_rent: string;
  deposit: string;
  bedrooms: number;
  area_sqm: string | null;
  occupancy_status: "available" | "reserved" | "occupied";
  listing: Listing | null;
}
export interface Property {
  id: string;
  landlord_id: string;
  title: string;
  description: string;
  city: string;
  address: string;
  postal_code: string;
  is_synthetic: boolean;
  amenities: string[];
}
export interface PropertyDetail extends Property {
  units: Unit[];
  images: PropertyImage[];
}
export interface PublicListing {
  id: string;
  property_id: string;
  rental_unit_id: string;
  title: string;
  description: string;
  city: string;
  address: string;
  postal_code: string;
  is_synthetic: boolean;
  kind: Kind;
  unit_name: string;
  monthly_rent: string;
  deposit: string;
  bedrooms: number;
  area_sqm: string | null;
  amenities: string[];
  images: PropertyImage[];
  available_from: string;
  available_until: string | null;
  available_now: boolean;
}
export interface Availability {
  available: boolean;
  reason: "available" | "outside_listing_window" | "rental_conflict";
}
export interface RentalContext {
  property_id?: string | null;
  property_title?: string | null;
  unit_name?: string | null;
}
export interface Application extends RentalContext {
  id: string;
  tenant_id: string;
  rental_unit_id: string;
  start_date: string;
  end_date: string;
  status: ApplicationStatus;
  note: string | null;
  review_note: string | null;
  created_at: string;
}
export interface Contract {
  id: string;
  rental_unit_id: string;
  property_id: string;
  property_title: string;
  unit_name: string;
  start_date: string;
  end_date: string;
  terminated_on: string | null;
  effective_end_date: string;
  monthly_rent: string;
  status: ContractStatus;
  tenant_id?: string;
  rental_request_id?: string;
}
export interface Visit extends RentalContext {
  id: string;
  tenant_id: string;
  rental_unit_id: string;
  requested_at: string;
  scheduled_at: string | null;
  scheduled_end_at: string | null;
  duration_minutes: number;
  status: VisitStatus;
  note: string | null;
  agency_note: string | null;
  assigned_admin_id?: string | null;
}
export interface Conversation {
  id: string;
  tenant_id: string;
  subject: string;
  unread_count: number;
  created_at: string;
  updated_at: string;
}
export interface Message {
  id: string;
  conversation_id: string;
  sender_type: "tenant" | "agency";
  body: string;
  read_at: string | null;
  created_at: string;
}
export interface SavedListing {
  id: string;
  listing_id: string;
  created_at: string;
  listing: PublicListing | null;
}
export interface OccupancyCounts {
  total_units: number;
  occupied_units: number;
  reserved_units: number;
  available_units: number;
  occupancy_percent: string;
  contracted_monthly_rent: string;
}
export interface OccupancySummary extends OccupancyCounts {
  as_of: string;
  properties: number;
}
export interface OccupancyItem extends OccupancyCounts {
  property_id: string;
  title: string;
  city: string;
}
export interface OccupancyReport {
  summary: OccupancySummary;
  items: OccupancyItem[];
  total: number;
  page: number;
  page_size: number;
}
export interface Statistics {
  role: Role;
  counts: Record<string, number>;
  occupancy: OccupancySummary | null;
}
