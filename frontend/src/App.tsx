import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowDownWideNarrow,
  ArrowUpRight,
  Bell,
  Bookmark,
  Bot,
  BriefcaseBusiness,
  Building2,
  Check,
  ChevronDown,
  Clock3,
  ExternalLink,
  FileText,
  LoaderCircle,
  Map,
  MapPin,
  RefreshCw,
  Search,
  Send,
  SlidersHorizontal,
  Sparkles,
  UploadCloud,
  X,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { JobMap } from "@/components/JobMap";
import { api, waitForOperation } from "@/lib/api/client";
import type { AlertCreate, JobRead, NotificationRead, ProfileRead, SearchRequest, SearchResult } from "@/lib/api/types";

const defaultSearch: SearchRequest = {
  keywords: "software engineer",
  location: "California",
  country: "US",
  language: "en",
  date_posted: "all",
  work_from_home: false,
  employment_types: [],
  job_requirements: [],
  distance_radius_miles: 50,
  max_jobs: 100,
};

function filtersFromProfile(profile: ProfileRead | undefined): SearchRequest {
  const saved = profile?.filter_data ?? {};
  return {
    ...defaultSearch,
    keywords: String(saved.keywords ?? defaultSearch.keywords),
    location: String(saved.location ?? defaultSearch.location),
    country: String(saved.country ?? defaultSearch.country).slice(0, 2).toUpperCase(),
    language: String(saved.language ?? defaultSearch.language),
    date_posted: (saved.date_posted as SearchRequest["date_posted"]) ?? "all",
    work_from_home: Boolean(saved.work_from_home),
    employment_types: (saved.employment_types as string[] | undefined) ?? [],
    job_requirements: (saved.job_requirements as string[] | undefined) ?? [],
    distance_radius_miles: Number(saved.distance_radius_miles ?? saved.distance_radius ?? 50),
    max_jobs: Number(saved.max_jobs ?? 100),
  };
}

function dateLabel(value: string | null): string {
  if (!value) return "Recently posted";
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return "Recently posted";
  const days = Math.max(0, Math.floor((Date.now() - date.valueOf()) / 86_400_000));
  return days === 0 ? "Today" : days === 1 ? "1 day ago" : `${days} days ago`;
}

function salaryLabel(job: JobRead): string | null {
  if (job.job_min_salary == null && job.job_max_salary == null) return null;
  const amount = [job.job_min_salary, job.job_max_salary]
    .filter((value): value is number => value != null)
    .map((value) => `$${Math.round(value / 1000)}k`)
    .join(" – ");
  return `${amount}${job.job_salary_period ? ` / ${job.job_salary_period.toLowerCase()}` : ""}`;
}

function highlightsFor(job: JobRead): string[] {
  const highlights = job.job_highlights;
  if (Array.isArray(highlights)) return highlights.filter((item): item is string => typeof item === "string");
  if (highlights && typeof highlights === "object") {
    return Object.values(highlights).flatMap((value) =>
      Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [],
    );
  }
  return [];
}

function ResultRow({
  job,
  selected,
  bookmarked,
  onSelect,
  onBookmark,
}: {
  job: JobRead;
  selected: boolean;
  bookmarked: boolean;
  onSelect: () => void;
  onBookmark: () => void;
}) {
  const salary = salaryLabel(job);
  return (
    <div className={`group relative rounded-2xl border p-4 transition ${selected ? "border-teal-700 bg-teal-50/55 shadow-sm" : "border-slate-200 bg-white hover:border-slate-300 hover:shadow-sm"}`}>
      <button className="absolute inset-0 rounded-2xl text-left" aria-label={`View ${job.title}`} onClick={onSelect} />
      <div className="relative pointer-events-none flex gap-3">
        <div className="grid size-10 shrink-0 place-items-center rounded-xl border border-slate-100 bg-slate-50 text-slate-500">
          {job.company?.logo_url ? <img className="size-8 rounded-lg object-contain" src={job.company.logo_url} alt="" /> : <Building2 className="size-4" />}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <p className="truncate text-[14px] font-semibold tracking-tight text-slate-900">{job.title}</p>
              <p className="mt-0.5 truncate text-xs font-medium text-slate-600">{job.company?.name ?? "Company not listed"}</p>
            </div>
            <button
              aria-label={bookmarked ? "Remove saved job" : "Save job"}
              className="pointer-events-auto -mr-1 -mt-1 grid size-8 shrink-0 place-items-center rounded-lg text-slate-400 transition hover:bg-white hover:text-teal-700"
              onClick={(event) => { event.stopPropagation(); onBookmark(); }}
            >
              <Bookmark className={`size-4 ${bookmarked ? "fill-teal-700 text-teal-700" : ""}`} />
            </button>
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-slate-500">
            <span className="inline-flex items-center gap-1"><MapPin className="size-3" />{job.location ?? ([job.city, job.state].filter(Boolean).join(", ") || "Location not listed")}</span>
            <span className="inline-flex items-center gap-1"><Clock3 className="size-3" />{dateLabel(job.posted_at_utc)}</span>
          </div>
          <div className="mt-3 flex flex-wrap gap-1.5">
            {job.is_remote && <Badge className="border-teal-100 bg-teal-50 px-2 py-0.5 text-[10px] text-teal-800">Remote</Badge>}
            {job.employment_type?.slice(0, 1).map((type) => <Badge key={type} className="px-2 py-0.5 text-[10px]">{type.replaceAll("_", " ")}</Badge>)}
            {salary && <span className="ml-auto self-center text-[11px] font-semibold text-slate-700">{salary}</span>}
          </div>
        </div>
      </div>
    </div>
  );
}

function NotificationMenu({
  notifications,
  onRead,
}: {
  notifications: NotificationRead[];
  onRead: (notificationId: number) => void;
}) {
  const [open, setOpen] = useState(false);
  const unreadCount = notifications.filter((item) => !item.read_at).length;
  return (
    <div className="relative">
      <Button aria-label={`Notifications${unreadCount ? `, ${unreadCount} unread` : ""}`} className="relative border-slate-200 bg-white" size="icon" variant="outline" onClick={() => setOpen((value) => !value)}>
        <Bell className="size-4" />
        {unreadCount > 0 && <span className="absolute -right-1 -top-1 grid size-4.5 place-items-center rounded-full bg-teal-700 text-[9px] font-bold text-white">{unreadCount > 9 ? "9+" : unreadCount}</span>}
      </Button>
      {open && (
        <div className="absolute right-0 top-12 z-50 w-[min(22rem,calc(100vw-2rem))] rounded-2xl border border-slate-200 bg-white p-3 shadow-xl">
          <div className="flex items-center justify-between px-1 pb-2"><h2 className="text-sm font-semibold">New job matches</h2><span className="text-xs text-slate-500">{unreadCount} unread</span></div>
          {notifications.length === 0 ? <p className="p-4 text-center text-xs leading-5 text-slate-500">New matches from your saved alerts will appear here.</p> : (
            <div className="max-h-80 space-y-2 overflow-auto">
              {notifications.map((item) => <div key={item.id} className={`rounded-xl border p-3 ${item.read_at ? "" : "border-teal-100 bg-teal-50/50"}`}>
                <div className="flex items-start justify-between gap-2"><div><p className="text-xs font-semibold text-slate-800">{item.title}</p><p className="mt-1 text-[11px] text-slate-500">{item.company_name ?? item.alert_name} · {item.alert_name}</p></div>
                  {!item.read_at && <button className="grid size-7 shrink-0 place-items-center rounded-lg text-teal-800 hover:bg-teal-100" aria-label="Mark as read" onClick={() => onRead(item.id)}><Check className="size-3.5" /></button>}
                </div>
                {item.apply_link && <a className="mt-2 inline-flex items-center gap-1 text-[11px] font-semibold text-teal-800" href={item.apply_link} target="_blank" rel="noreferrer">Open job <ExternalLink className="size-3" /></a>}
              </div>)}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function App() {
  const queryClient = useQueryClient();
  const [profileName, setProfileName] = useState(() => localStorage.getItem("job-match-profile") ?? "");
  const [filters, setFilters] = useState<SearchRequest>(defaultSearch);
  const [results, setResults] = useState<SearchResult | null>(null);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [resultsMode, setResultsMode] = useState<"list" | "map">("list");
  const [searchProgress, setSearchProgress] = useState("");
  const [chatPrompt, setChatPrompt] = useState("");
  const [alertFeedback, setAlertFeedback] = useState("");
  const [chatMessages, setChatMessages] = useState<Array<{ role: "user" | "assistant"; text: string }>>([]);
  const [chatProgress, setChatProgress] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);
  const chatScroll = useRef<HTMLDivElement>(null);

  const profilesQuery = useQuery({ queryKey: ["profiles"], queryFn: api.getProfiles });
  useEffect(() => {
    const profiles = profilesQuery.data;
    if (!profiles?.length) return;
    if (!profiles.some((profile) => profile.name === profileName)) {
      setProfileName(profiles.find((profile) => profile.is_active)?.name ?? profiles[0].name);
    }
  }, [profilesQuery.data, profileName]);
  useEffect(() => {
    if (profileName) localStorage.setItem("job-match-profile", profileName);
    const profile = profilesQuery.data?.find((item) => item.name === profileName);
    if (profile) setFilters(filtersFromProfile(profile));
  }, [profileName, profilesQuery.data]);
  useEffect(() => { setChatMessages([]); }, [profileName]);
  useEffect(() => { chatScroll.current?.scrollTo({ top: chatScroll.current.scrollHeight, behavior: "smooth" }); }, [chatMessages, chatProgress]);

  const bookmarksQuery = useQuery({ queryKey: ["bookmarks", profileName], queryFn: () => api.getBookmarks(profileName), enabled: Boolean(profileName) });
  const resumeQuery = useQuery({ queryKey: ["resume", profileName], queryFn: () => api.getResume(profileName), enabled: Boolean(profileName) });
  const notificationsQuery = useQuery({ queryKey: ["notifications", profileName], queryFn: () => api.getNotifications(profileName), enabled: Boolean(profileName), refetchInterval: 60_000 });
  const bookmarkedIds = useMemo(() => new Set(bookmarksQuery.data?.map((job) => job.job_id) ?? []), [bookmarksQuery.data]);
  const selectedJob = results?.jobs.find((job) => job.job_id === selectedJobId) ?? results?.jobs[0] ?? null;
  const visibleJobIds = results?.job_ids ?? [];
  const notEmbeddedCount = results?.jobs.filter((job) => !job.is_embedded).length ?? 0;

  const searchMutation = useMutation({
    mutationFn: async () => {
      if (!profileName) throw new Error("Choose a profile before searching.");
      setSearchProgress("Starting search");
      const operation = await api.startSearch(profileName, filters);
      const completed = await waitForOperation<SearchResult>(operation.id, { onProgress: (current) => setSearchProgress(current.progress ?? "Searching jobs") });
      if (!completed.result) throw new Error("Search completed without results.");
      return completed.result;
    },
    onSuccess: (result) => {
      setResults(result);
      setSelectedJobId(result.jobs[0]?.job_id ?? null);
      setChatMessages([]);
      setSearchProgress("");
    },
    onError: () => setSearchProgress(""),
  });
  const bookmarkMutation = useMutation({
    mutationFn: async ({ jobId, saved }: { jobId: string; saved: boolean }) => saved ? api.removeBookmark(profileName, jobId) : api.addBookmark(profileName, jobId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["bookmarks", profileName] }),
  });
  const markReadMutation = useMutation({
    mutationFn: (id: number) => api.markNotificationRead(profileName, id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["notifications", profileName] }),
  });
  const createAlertMutation = useMutation({
    mutationFn: (payload: AlertCreate) => api.createAlert(profileName, payload),
    onSuccess: () => {
      setAlertFeedback("Daily alert saved. The first check builds a baseline; new matches will appear in notifications.");
      queryClient.invalidateQueries({ queryKey: ["alerts", profileName] });
    },
    onError: (error) => setAlertFeedback(error instanceof Error ? error.message : "Could not save this alert."),
  });
  const embedMutation = useMutation({
    mutationFn: async () => {
      if (!profileName || !visibleJobIds.length) throw new Error("Search for jobs first.");
      setChatProgress("Preparing job context…");
      const operation = await api.startEmbedding(profileName, { job_ids: visibleJobIds });
      const completed = await waitForOperation(operation.id, { onProgress: (current) => setChatProgress(current.progress ?? "Indexing job context…") });
      return completed;
    },
    onSuccess: () => {
      setChatProgress("");
      // Search result DTOs are a snapshot; the local embedding status is refreshed below.
      if (results) setResults({ ...results, jobs: results.jobs.map((job) => ({ ...job, is_embedded: true, is_summarized: true })) });
    },
    onError: (error) => setChatProgress(error instanceof Error ? error.message : "Could not prepare job context"),
  });
  const uploadResumeMutation = useMutation({
    mutationFn: async (file: File) => {
      setChatProgress("Uploading and reading your resume…");
      const operation = await api.uploadResume(profileName, file);
      return waitForOperation(operation.id, { onProgress: (current) => setChatProgress(current.progress ?? "Preparing resume…") });
    },
    onSuccess: () => {
      setChatProgress("");
      queryClient.invalidateQueries({ queryKey: ["resume", profileName] });
      queryClient.invalidateQueries({ queryKey: ["profiles"] });
    },
    onError: (error) => setChatProgress(error instanceof Error ? error.message : "Resume processing failed"),
  });
  const deleteResumeMutation = useMutation({
    mutationFn: () => api.deleteResume(profileName),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["resume", profileName] });
      queryClient.invalidateQueries({ queryKey: ["profiles"] });
      setChatMessages([]);
    },
  });
  const chatMutation = useMutation({
    mutationFn: async (prompt: string) => {
      setChatProgress("Searching job context…");
      return api.sendChat(profileName, prompt, visibleJobIds);
    },
    onSuccess: (response) => {
      setChatMessages((current) => [...current, { role: "assistant", text: response.answer }]);
      setChatProgress("");
    },
    onError: (error) => {
      setChatMessages((current) => [...current, { role: "assistant", text: error instanceof Error ? error.message : "The assistant could not answer right now." }]);
      setChatProgress("");
    },
  });

  function updateFilter<Key extends keyof SearchRequest>(key: Key, value: SearchRequest[Key]) {
    setFilters((current) => ({ ...current, [key]: value }));
  }

  function sendChat() {
    const prompt = chatPrompt.trim();
    if (!prompt || !visibleJobIds.length || notEmbeddedCount > 0 || chatMutation.isPending) return;
    setChatMessages((current) => [...current, { role: "user", text: prompt }]);
    setChatPrompt("");
    chatMutation.mutate(prompt);
  }

  const unreadNotifications = notificationsQuery.data ?? [];
  const searchError = searchMutation.error instanceof Error ? searchMutation.error.message : null;
  const profileError = profilesQuery.error instanceof Error ? profilesQuery.error.message : null;

  return (
    <div className="min-h-screen bg-[#f6f8f7] text-slate-900">
      <header className="sticky top-0 z-40 border-b border-slate-200/80 bg-white/95 backdrop-blur">
        <div className="mx-auto flex h-17 max-w-[1800px] items-center justify-between gap-4 px-5 xl:px-8">
          <div className="flex shrink-0 items-center gap-3">
            <div className="grid size-9 place-items-center rounded-xl bg-teal-800 text-white"><BriefcaseBusiness className="size-4.5" /></div>
            <div><div className="text-[15px] font-bold tracking-tight">job<span className="text-teal-700">match</span></div><div className="text-[10px] font-medium uppercase tracking-[0.14em] text-slate-400">Opportunity workspace</div></div>
          </div>
          <div className="hidden items-center gap-1 rounded-full bg-slate-100 p-1 md:flex">
            <span className="rounded-full bg-white px-4 py-2 text-xs font-semibold text-slate-900 shadow-sm">Discover</span>
            <span className="px-4 py-2 text-xs font-medium text-slate-500">Saved jobs <span className="ml-1 text-slate-400">{bookmarksQuery.data?.length ?? 0}</span></span>
          </div>
          <div className="flex items-center gap-3">
            <span className={`hidden items-center gap-1.5 text-[11px] font-medium sm:flex ${profilesQuery.isError ? "text-rose-600" : "text-slate-500"}`}><span className={`size-1.5 rounded-full ${profilesQuery.isSuccess ? "bg-emerald-500" : profilesQuery.isError ? "bg-rose-500" : "bg-amber-400"}`} />{profilesQuery.isSuccess ? "Connected" : profilesQuery.isError ? "API unavailable" : "Connecting"}</span>
            <NotificationMenu notifications={unreadNotifications} onRead={(id) => markReadMutation.mutate(id)} />
            <div className="relative">
              <select aria-label="Active profile" className="h-9 max-w-36 appearance-none rounded-xl border border-slate-200 bg-white pl-3 pr-8 text-xs font-semibold text-slate-700 outline-none focus:ring-2 focus:ring-teal-700/20" disabled={!profilesQuery.data?.length} value={profileName} onChange={(event) => { setProfileName(event.target.value); setResults(null); setSelectedJobId(null); }}>
                {(profilesQuery.data ?? []).map((profile) => <option key={profile.name} value={profile.name}>{profile.name}</option>)}
              </select><ChevronDown className="pointer-events-none absolute right-2.5 top-2.5 size-3.5 text-slate-400" />
            </div>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-[1800px] px-5 pb-8 pt-6 xl:px-8">
        <section className="mb-5 flex flex-wrap items-end justify-between gap-4">
          <div><div className="mb-1 flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.13em] text-teal-800"><Sparkles className="size-3.5" /> Curated for {profileName || "your profile"}</div><h1 className="text-2xl font-bold tracking-tight sm:text-[28px]">Find your next opportunity</h1><p className="mt-1 text-sm text-slate-500">Search, compare, and get a second opinion from AI.</p></div>
          <div className="flex items-center gap-2 text-xs text-slate-500"><span className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-3 py-1.5"><BriefcaseBusiness className="size-3.5 text-teal-700" />{results?.total ?? 0} opportunities</span></div>
        </section>

        <form className="mb-5 grid gap-2 rounded-2xl border border-slate-200 bg-white p-2.5 shadow-[0_2px_12px_-8px_rgba(15,23,42,.18)] md:grid-cols-[minmax(220px,1.25fr)_minmax(170px,.8fr)_150px_auto_auto]" onSubmit={(event) => { event.preventDefault(); searchMutation.mutate(); }}>
          <label className="flex h-11 items-center gap-2.5 rounded-xl px-3 focus-within:bg-slate-50"><Search className="size-4 shrink-0 text-slate-400" /><Input className="h-10 border-0 bg-transparent px-0 shadow-none focus-visible:ring-0" value={filters.keywords} onChange={(event) => updateFilter("keywords", event.target.value)} placeholder="Role, skill, or company" /></label>
          <label className="flex h-11 items-center gap-2.5 rounded-xl border-l border-slate-100 px-3 focus-within:bg-slate-50"><MapPin className="size-4 shrink-0 text-slate-400" /><Input className="h-10 border-0 bg-transparent px-0 shadow-none focus-visible:ring-0" value={filters.location ?? ""} onChange={(event) => updateFilter("location", event.target.value)} placeholder="City or remote" /></label>
          <label className="flex h-11 items-center gap-2 rounded-xl border-l border-slate-100 px-3"><ArrowDownWideNarrow className="size-4 shrink-0 text-slate-400" /><select className="h-10 min-w-0 flex-1 bg-transparent text-xs font-medium outline-none" value={filters.date_posted} onChange={(event) => updateFilter("date_posted", event.target.value as SearchRequest["date_posted"])}><option value="all">Any date</option><option value="today">Today</option><option value="3days">Past 3 days</option><option value="week">This week</option><option value="month">This month</option></select></label>
          <label className="flex h-11 items-center justify-center gap-2 rounded-xl px-3 text-xs font-medium text-slate-600"><input className="accent-teal-700" type="checkbox" checked={filters.work_from_home ?? false} onChange={(event) => updateFilter("work_from_home", event.target.checked)} />Remote</label>
          <Button className="h-11 rounded-xl bg-teal-800 px-5 text-xs hover:bg-teal-900" disabled={!profileName || searchMutation.isPending} type="submit">{searchMutation.isPending ? <LoaderCircle className="size-4 animate-spin" /> : <Search className="size-4" />}{searchMutation.isPending ? "Searching" : "Search jobs"}</Button>
        </form>

        {(searchError || profileError) && <div role="alert" className="mb-4 flex items-center justify-between rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800">{searchError ?? profileError}<button aria-label="Dismiss error" onClick={() => searchMutation.reset()}><X className="size-4" /></button></div>}

        <div className="mb-3 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 text-xs text-slate-500"><SlidersHorizontal className="size-3.5" />{searchMutation.isPending ? searchProgress || "Searching" : results ? `Showing ${results.jobs.length} results` : "Ready to search"}{filters.location ? ` near ${filters.location}` : ""}</div>
          {results && <div className="flex gap-2"><Button className="h-8 gap-1.5 rounded-lg border-slate-200 bg-white px-3 text-[11px]" size="sm" variant="outline" disabled={createAlertMutation.isPending} onClick={() => createAlertMutation.mutate({ name: filters.keywords, filters, frequency: "daily" })}><Bell className="size-3.5" />{createAlertMutation.isPending ? "Saving…" : "Save daily alert"}</Button><Button className="h-8 gap-1.5 rounded-lg border-slate-200 bg-white px-3 text-[11px]" size="sm" variant="outline" onClick={() => searchMutation.mutate()}><RefreshCw className="size-3.5" />Refresh results</Button></div>}
        </div>
        {alertFeedback && <p role="status" className={`mb-3 rounded-xl px-3 py-2 text-xs ${createAlertMutation.isError ? "bg-rose-50 text-rose-700" : "bg-teal-50 text-teal-900"}`}>{alertFeedback}</p>}

        <div className="grid items-start gap-4 2xl:grid-cols-[minmax(290px,.78fr)_minmax(430px,1.25fr)_minmax(330px,.85fr)] xl:grid-cols-[minmax(280px,.75fr)_minmax(650px,1.65fr)]">
          <Card className="overflow-hidden rounded-2xl border-slate-200 bg-white shadow-[0_6px_24px_-18px_rgba(15,23,42,.25)]">
            <CardHeader className="flex-row items-center justify-between border-b border-slate-100 px-4 py-3.5">
              <div><CardTitle className="text-sm">Search results <span className="ml-1.5 rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-semibold text-slate-500">{results?.jobs.length ?? 0}</span></CardTitle><p className="mt-1 text-[11px] text-slate-500">Ranked by relevance</p></div>
              <div className="flex rounded-lg bg-slate-100 p-0.5">
                <button className={`grid size-7 place-items-center rounded-md ${resultsMode === "list" ? "bg-white text-teal-800 shadow-sm" : "text-slate-400"}`} aria-label="List view" onClick={() => setResultsMode("list")}><BriefcaseBusiness className="size-3.5" /></button>
                <button className={`grid size-7 place-items-center rounded-md ${resultsMode === "map" ? "bg-white text-teal-800 shadow-sm" : "text-slate-400"}`} aria-label="Map view" onClick={() => setResultsMode("map")}><Map className="size-3.5" /></button>
              </div>
            </CardHeader>
            <CardContent className="p-3">
              {resultsMode === "map" && results?.jobs.length ? <JobMap jobs={results.jobs} selectedJobId={selectedJob?.job_id ?? null} onSelect={setSelectedJobId} /> : null}
              {resultsMode === "list" && results?.jobs.length ? <div className="max-h-[calc(100vh-280px)] min-h-80 space-y-2 overflow-y-auto pr-1">
                {results.jobs.map((job) => <ResultRow key={job.job_id} job={job} selected={job.job_id === selectedJob?.job_id} bookmarked={bookmarkedIds.has(job.job_id)} onSelect={() => setSelectedJobId(job.job_id)} onBookmark={() => bookmarkMutation.mutate({ jobId: job.job_id, saved: bookmarkedIds.has(job.job_id) })} />)}
              </div> : null}
              {!results && <div className="flex min-h-107.5 flex-col items-center justify-center px-7 text-center"><div className="mb-4 grid size-12 place-items-center rounded-2xl bg-teal-50 text-teal-800"><Search className="size-5" /></div><p className="text-sm font-semibold">Your shortlist starts here</p><p className="mt-2 max-w-55 text-xs leading-5 text-slate-500">Choose a role and location above to discover matching opportunities.</p></div>}
              {results?.jobs.length === 0 && <div className="flex min-h-64 flex-col items-center justify-center px-6 text-center"><p className="text-sm font-semibold">No matches this time</p><p className="mt-1 text-xs text-slate-500">Try a broader keyword or location.</p></div>}
            </CardContent>
          </Card>

          <Card className="overflow-hidden rounded-2xl border-slate-200 bg-white shadow-[0_6px_24px_-18px_rgba(15,23,42,.25)] xl:col-span-1 2xl:col-span-1">
            <CardContent className="p-0">
              {!selectedJob ? <div className="flex min-h-125 flex-col items-center justify-center px-8 text-center"><div className="mb-4 grid size-12 place-items-center rounded-2xl bg-slate-100 text-slate-500"><FileText className="size-5" /></div><p className="text-sm font-semibold">Job details</p><p className="mt-1 max-w-xs text-xs leading-5 text-slate-500">Select a listing to review its description, compensation, and application link.</p></div> : <JobDetails job={selectedJob} bookmarked={bookmarkedIds.has(selectedJob.job_id)} onBookmark={() => bookmarkMutation.mutate({ jobId: selectedJob.job_id, saved: bookmarkedIds.has(selectedJob.job_id) })} />}
            </CardContent>
          </Card>

          <Card className="overflow-hidden rounded-2xl border-slate-200 bg-white shadow-[0_6px_24px_-18px_rgba(15,23,42,.25)] xl:col-span-2 2xl:col-span-1">
            <CardHeader className="border-b border-slate-100 px-4 py-3.5"><div className="flex items-center gap-2"><span className="grid size-8 place-items-center rounded-xl bg-teal-800 text-white"><Sparkles className="size-4" /></span><div><CardTitle className="text-sm">Career copilot</CardTitle><p className="mt-0.5 text-[11px] text-slate-500">Grounded in your resume and results</p></div><span className="ml-auto size-2 rounded-full bg-emerald-500" /></div></CardHeader>
            <CardContent className="p-0">
              <div className="border-b border-slate-100 px-4 py-3">
                <input ref={fileInput} className="hidden" type="file" accept=".pdf,.docx,.txt,.html,.png,.jpg,.jpeg" onChange={(event) => { const file = event.target.files?.[0]; if (file) uploadResumeMutation.mutate(file); event.currentTarget.value = ""; }} />
                {resumeQuery.data?.has_resume ? <div className="flex items-start gap-3"><span className="grid size-9 shrink-0 place-items-center rounded-xl bg-violet-50 text-violet-700"><FileText className="size-4" /></span><div className="min-w-0 flex-1"><p className="truncate text-xs font-semibold text-slate-800">{resumeQuery.data.filename ?? "Resume uploaded"}</p><p className="mt-0.5 text-[10px] text-slate-500">{resumeQuery.data.summary ? "AI summary ready" : "Resume attached"}</p></div><button aria-label="Remove resume" className="grid size-7 place-items-center rounded-lg text-slate-400 hover:bg-slate-100" onClick={() => deleteResumeMutation.mutate()}><X className="size-3.5" /></button></div> : <button className="flex w-full items-center gap-3 rounded-xl border border-dashed border-slate-300 p-3 text-left transition hover:border-teal-600 hover:bg-teal-50/40" onClick={() => fileInput.current?.click()}><span className="grid size-9 shrink-0 place-items-center rounded-xl bg-slate-100 text-slate-600"><UploadCloud className="size-4" /></span><span><span className="block text-xs font-semibold">Add your resume</span><span className="mt-0.5 block text-[10px] text-slate-500">Get personalized job-fit guidance</span></span></button>}
                {resumeQuery.data?.summary && <div className="mt-3 max-h-28 overflow-auto rounded-xl bg-slate-50 p-3 text-[11px] leading-5 text-slate-600">{resumeQuery.data.summary}</div>}
                {uploadResumeMutation.isPending && <p className="mt-2 text-[10px] text-teal-800">{chatProgress || "Preparing your resume…"}</p>}
                {notEmbeddedCount > 0 && <button className="mt-3 flex w-full items-center justify-center gap-1.5 rounded-xl bg-teal-50 px-3 py-2 text-[11px] font-semibold text-teal-900 hover:bg-teal-100 disabled:opacity-50" disabled={embedMutation.isPending || !visibleJobIds.length} onClick={() => embedMutation.mutate()}>{embedMutation.isPending ? <LoaderCircle className="size-3.5 animate-spin" /> : <Sparkles className="size-3.5" />}{embedMutation.isPending ? chatProgress || "Preparing jobs…" : `Prepare ${notEmbeddedCount} jobs for AI`}</button>}
              </div>

              <div ref={chatScroll} className="flex h-82.5 flex-col gap-3 overflow-y-auto px-4 py-4">
                {chatMessages.length === 0 && <div className="mt-auto rounded-2xl rounded-tl-sm bg-slate-50 p-3.5"><div className="mb-2 flex items-center gap-2 text-[11px] font-semibold text-slate-700"><Bot className="size-3.5 text-teal-800" />Your job-search copilot</div><p className="text-[11px] leading-5 text-slate-600">Ask me to compare roles, find the best fit for your experience, or explain compensation and trade-offs.</p><div className="mt-3 flex flex-wrap gap-1.5">{["Which role fits my resume?", "Compare the top two", "Show remote options"].map((suggestion) => <button key={suggestion} className="rounded-full border border-slate-200 bg-white px-2.5 py-1.5 text-[10px] font-medium text-slate-600 hover:border-teal-400 hover:text-teal-800" disabled={!visibleJobIds.length || notEmbeddedCount > 0} onClick={() => { setChatMessages((current) => [...current, { role: "user", text: suggestion }]); chatMutation.mutate(suggestion); }}>{suggestion}</button>)}</div></div>}
                {chatMessages.map((message, index) => <div key={`${message.role}-${index}`} className={`max-w-[92%] whitespace-pre-wrap rounded-2xl px-3.5 py-3 text-[11px] leading-5 ${message.role === "user" ? "ml-auto rounded-tr-sm bg-teal-800 text-white" : "mr-auto rounded-tl-sm bg-slate-50 text-slate-700"}`}>{message.text}</div>)}
                {chatMutation.isPending && <div className="mr-auto inline-flex items-center gap-2 rounded-2xl rounded-tl-sm bg-slate-50 px-3.5 py-3 text-[11px] text-slate-500"><LoaderCircle className="size-3.5 animate-spin" />{chatProgress || "Thinking…"}</div>}
                {!visibleJobIds.length && <p className="mt-auto text-center text-[10px] text-slate-400">Search for jobs to start a conversation.</p>}
              </div>
              <form className="border-t border-slate-100 p-3" onSubmit={(event) => { event.preventDefault(); sendChat(); }}><div className="flex items-end gap-2 rounded-xl border border-slate-200 bg-white p-1.5 focus-within:border-teal-600"><textarea className="max-h-24 min-h-9 flex-1 resize-none bg-transparent px-2 py-2 text-xs outline-none placeholder:text-slate-400" value={chatPrompt} onChange={(event) => setChatPrompt(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); sendChat(); } }} placeholder={!visibleJobIds.length ? "Search for jobs to start…" : notEmbeddedCount > 0 ? "Prepare job context to start chatting…" : "Ask about these opportunities…"} disabled={!visibleJobIds.length || notEmbeddedCount > 0} /><Button aria-label="Send message" className="size-8 rounded-lg bg-teal-800 hover:bg-teal-900" size="icon" disabled={!chatPrompt.trim() || chatMutation.isPending || !visibleJobIds.length || notEmbeddedCount > 0}><Send className="size-3.5" /></Button></div><p className="mt-2 text-center text-[9px] text-slate-400">AI can make mistakes. Verify details with the employer.</p></form>
            </CardContent>
          </Card>
        </div>
        <footer className="mt-5 flex flex-wrap items-center justify-between gap-2 px-1 text-[10px] text-slate-400"><span>Search by JSearch · AI context is private to this profile</span><span>{results?.search_id ? `Search ${results.search_id.slice(0, 8)}` : "Job discovery workspace"}</span></footer>
      </main>
    </div>
  );
}

function JobDetails({ job, bookmarked, onBookmark }: { job: JobRead; bookmarked: boolean; onBookmark: () => void }) {
  const highlights = highlightsFor(job);
  const salary = salaryLabel(job);
  return (
    <article>
      <div className="border-b border-slate-100 p-5 sm:p-6">
        <div className="flex items-start gap-4">
          <div className="grid size-12 shrink-0 place-items-center rounded-2xl border border-slate-100 bg-slate-50 text-slate-500">{job.company?.logo_url ? <img src={job.company.logo_url} alt="" className="size-9 rounded-xl object-contain" /> : <Building2 className="size-5" />}</div>
          <div className="min-w-0 flex-1"><p className="text-[11px] font-medium text-slate-500">{job.company?.name ?? "Company not listed"}</p><h2 className="mt-1 text-xl font-bold leading-tight tracking-tight">{job.title}</h2><p className="mt-2 flex items-center gap-1.5 text-xs text-slate-500"><MapPin className="size-3.5" />{job.location ?? ([job.city, job.state, job.country].filter(Boolean).join(", ") || "Location not listed")}</p></div>
          <Button aria-label={bookmarked ? "Remove saved job" : "Save job"} className="size-9 rounded-xl" size="icon" variant="outline" onClick={onBookmark}><Bookmark className={`size-4 ${bookmarked ? "fill-teal-700 text-teal-700" : ""}`} /></Button>
        </div>
        <div className="mt-5 flex flex-wrap gap-2">{job.is_remote && <Badge className="border-teal-100 bg-teal-50 text-teal-800">Remote</Badge>}{job.employment_type?.map((type) => <Badge key={type}>{type.replaceAll("_", " ")}</Badge>)}{salary && <Badge className="border-amber-200 bg-amber-50 text-amber-900">{salary}</Badge>}</div>
        <div className="mt-5 flex gap-2"><a className={`inline-flex h-10 flex-1 items-center justify-center gap-2 rounded-xl bg-teal-800 text-xs font-semibold text-white transition hover:bg-teal-900 ${job.apply_link ? "" : "pointer-events-none opacity-45"}`} href={job.apply_link ?? undefined} target="_blank" rel="noreferrer">Apply now <ArrowUpRight className="size-3.5" /></a>{job.job_google_link && <a aria-label="Open job source" className="grid size-10 place-items-center rounded-xl border border-slate-200 text-slate-600 hover:bg-slate-50" href={job.job_google_link} target="_blank" rel="noreferrer"><ExternalLink className="size-4" /></a>}</div>
        <p className="mt-3 text-[10px] text-slate-400">{job.publisher ?? "Job listing"} <span className="mx-1">·</span> {dateLabel(job.posted_at_utc)}</p>
      </div>
      <div className="max-h-[calc(100vh-380px)] space-y-6 overflow-y-auto p-5 sm:p-6">
        {highlights.length > 0 && <section><h3 className="mb-3 text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Role highlights</h3><ul className="space-y-2">{highlights.slice(0, 8).map((highlight, index) => <li key={`${index}-${highlight.slice(0, 24)}`} className="flex gap-2.5 text-xs leading-5 text-slate-600"><span className="mt-1.75 size-1.5 shrink-0 rounded-full bg-teal-700" />{highlight}</li>)}</ul></section>}
        {job.job_benefits && <section><h3 className="mb-2 text-xs font-bold uppercase tracking-[0.12em] text-slate-500">Benefits</h3><p className="text-xs leading-5 text-slate-600">{job.job_benefits}</p></section>}
        <section><h3 className="mb-3 text-xs font-bold uppercase tracking-[0.12em] text-slate-500">About the role</h3><div className="whitespace-pre-line text-xs leading-6 text-slate-600">{job.job_summary ?? job.description ?? "The publisher has not provided a full description."}</div></section>
        <div className="rounded-xl border border-slate-100 bg-slate-50 px-3.5 py-3 text-[10px] text-slate-500"><span className="font-semibold text-slate-700">Job ID</span> · {job.job_id}</div>
      </div>
    </article>
  );
}
