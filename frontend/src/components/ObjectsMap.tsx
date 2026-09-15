import L from "leaflet";
import { useEffect, useRef } from "react";
import "leaflet/dist/leaflet.css";
import type { ObjectsGeoJson } from "../api/types";

// WKT типа "POINT (lon lat)" — единственный формат, который нам нужно уметь читать сейчас.
function parsePointWkt(wkt: string): [number, number] | null {
  const m = /POINT\s*\(\s*([-\d.]+)\s+([-\d.]+)\s*\)/i.exec(wkt);
  if (!m) return null;
  return [parseFloat(m[2]), parseFloat(m[1])]; // [lat, lon] для Leaflet
}

export function ObjectsMap({ data }: { data: ObjectsGeoJson }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    mapRef.current = L.map(containerRef.current).setView([55.75, 37.62], 10); // Москва по умолчанию
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "© OpenStreetMap",
    }).addTo(mapRef.current);
    return () => {
      mapRef.current?.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!mapRef.current) return;
    const markers: L.Marker[] = [];
    for (const f of data.features) {
      const point = parsePointWkt(f.geometry_wkt);
      if (!point) continue;
      const marker = L.marker(point).addTo(mapRef.current).bindPopup(String(f.properties.name ?? ""));
      markers.push(marker);
    }
    return () => {
      markers.forEach((m) => m.remove());
    };
  }, [data]);

  return <div ref={containerRef} style={{ height: "420px", borderRadius: 8 }} />;
}
