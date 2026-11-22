export interface CompanyRead {
  name: string;
  logo_url: string | null;
  website: string | null;
}

export interface JobRead {
  id: number;
  job_id: string;
  title: string;
  description: string | null;
  country: string | null;
  state: string | null;
  city: string | null;
  location: string | null;
  job_latitude: number | null;
  job_longitude: number | null;
  posted_at_utc: string | null;
  is_remote: boolean | null;
  employment_type: string[] | null;
  job_min_salary: number | null;
  job_max_salary: number | null;
  job_salary_period: string | null;
  publisher: string | null;
  apply_link: string | null;
  apply_options: unknown;
  job_google_link: string | null;
  job_highlights: unknown;
  job_benefits: string | null;
  is_summarized: boolean;
  is_embedded: boolean;
  job_summary: string | null;
  company: CompanyRead | null;
}

export interface ProfileRead {
  name: string;
  is_active: boolean;
  my_location: string | null;
  latitude: number | null;
  longitude: number | null;
  filter_data: Record<string, unknown>;
  favorite_job_ids: string[];
  resume_filename: string | null;
  resume_summary: string | null;
}

export interface ProfileCreate {
  name: string;
}

export interface SearchRequest {
  keywords: string;
  location?: string | null;
  country?: string;
  language?: string;
  date_posted?: "all" | "today" | "3days" | "week" | "month";
  work_from_home?: boolean;
  employment_types?: string[];
  job_requirements?: string[];
  distance_radius_miles?: number | null;
  max_jobs?: number;
}

export interface SearchResult {
  search_id: string;
  job_ids: string[];
  jobs: JobRead[];
  total: number;
}

export interface ChatRequest {
  prompt: string;
  job_ids: string[];
}

export interface ChatRead {
  answer: string;
}

export type OperationStatus = "queued" | "running" | "succeeded" | "failed";

export interface OperationRead<TResult = Record<string, unknown>> {
  id: string;
  kind: string;
  status: OperationStatus;
  progress: string | null;
  result: TResult | null;
  error: string | null;
  created_at: string;
  updated_at: string;
}

export interface BookmarkRead {
  job_id: string;
  is_bookmarked: boolean;
}

export interface ResumeRead {
  has_resume: boolean;
  filename: string | null;
  summary: string | null;
}

export interface EmbeddingRequest {
  job_ids: string[];
}

export interface AlertCreate {
  name: string;
  filters: SearchRequest;
  frequency?: "daily" | "weekly";
  is_enabled?: boolean;
}

export interface AlertUpdate {
  name?: string | null;
  filters?: SearchRequest | null;
  frequency?: "daily" | "weekly" | null;
  is_enabled?: boolean | null;
}

export interface AlertRead {
  id: number;
  profile_name: string;
  name: string;
  filters: Record<string, unknown>;
  frequency: "daily" | "weekly";
  is_enabled: boolean;
  created_at: string;
  last_run_at: string | null;
  next_run_at: string;
  baseline_complete: boolean;
  last_error: string | null;
  last_match_job_ids: string[];
}

export interface NotificationRead {
  id: number;
  alert_id: number;
  alert_name: string;
  job_id: string;
  title: string;
  company_name: string | null;
  location: string | null;
  apply_link: string | null;
  created_at: string;
  read_at: string | null;
}

export interface AlertRunResult {
  matched_job_ids: string[];
  new_job_ids: string[];
  jobs: JobRead[];
}

export interface ApiErrorPayload {
  detail?: unknown;
}
