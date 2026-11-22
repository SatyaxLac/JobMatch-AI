import { useEffect, useMemo } from "react";
import { MapContainer, Marker, Popup, TileLayer, useMap } from "react-leaflet";
import L from "leaflet";
import type { JobRead } from "@/lib/api/types";
import "leaflet/dist/leaflet.css";

function createMarkerIcon(selected: boolean) {
  return L.divIcon({
    className: "job-marker-shell",
    html: `<span class="job-marker${selected ? " job-marker-selected" : ""}"></span>`,
    iconSize: [22, 22],
    iconAnchor: [11, 11],
  });
}

function FitJobs({ jobs }: { jobs: JobRead[] }) {
  const map = useMap();
  const points = useMemo(() => jobs
    .filter((job) => job.job_latitude != null && job.job_longitude != null)
    .map((job) => [job.job_latitude as number, job.job_longitude as number] as [number, number]), [jobs]);
  useEffect(() => {
    if (points.length > 1) map.fitBounds(points, { padding: [36, 36], maxZoom: 12 });
    else if (points.length === 1) map.setView(points[0], 11);
  }, [map, points]);
  return null;
}

export function JobMap({
  jobs,
  selectedJobId,
  onSelect,
}: {
  jobs: JobRead[];
  selectedJobId: string | null;
  onSelect: (jobId: string) => void;
}) {
  const locatedJobs = useMemo(() => jobs.filter((job) => job.job_latitude != null && job.job_longitude != null), [jobs]);
  const center = useMemo<[number, number]>(() => {
    if (!locatedJobs.length) return [39.5, -98.35];
    return [
      locatedJobs.reduce((total, job) => total + (job.job_latitude ?? 0), 0) / locatedJobs.length,
      locatedJobs.reduce((total, job) => total + (job.job_longitude ?? 0), 0) / locatedJobs.length,
    ];
  }, [locatedJobs]);

  if (locatedJobs.length === 0) {
    return (
      <div className="flex h-105 flex-col items-center justify-center rounded-2xl border border-dashed bg-slate-50 px-8 text-center">
        <div className="mb-3 grid size-11 place-items-center rounded-full bg-white text-teal-700 shadow-sm">◎</div>
        <p className="font-semibold text-slate-800">No mapped locations yet</p>
        <p className="mt-1 max-w-xs text-sm leading-6 text-slate-500">These listings don’t include coordinates. Switch to list view to see every result.</p>
      </div>
    );
  }

  return (
    <div className="job-map overflow-hidden rounded-2xl border border-slate-200">
      <MapContainer center={center} zoom={5} scrollWheelZoom className="h-105 w-full">
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <FitJobs jobs={locatedJobs} />
        {locatedJobs.map((job) => (
          <Marker
            key={job.job_id}
            position={[job.job_latitude as number, job.job_longitude as number]}
            icon={createMarkerIcon(job.job_id === selectedJobId)}
            eventHandlers={{ click: () => onSelect(job.job_id) }}
          >
            <Popup>
              <div className="min-w-44">
                <p className="font-semibold">{job.title}</p>
                <p className="mt-1 text-sm text-slate-600">{job.company?.name ?? "Company not listed"}</p>
                <p className="mt-1 text-xs text-slate-500">{job.location ?? [job.city, job.state].filter(Boolean).join(", ")}</p>
              </div>
            </Popup>
          </Marker>
        ))}
      </MapContainer>
      <div className="border-t bg-white px-3 py-2 text-xs text-slate-500">
        {locatedJobs.length} of {jobs.length} results have map coordinates · OpenStreetMap
      </div>
    </div>
  );
}
