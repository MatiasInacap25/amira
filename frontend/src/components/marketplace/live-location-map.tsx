"use client";

import "leaflet/dist/leaflet.css";
import { divIcon } from "leaflet";
import { useEffect, useMemo } from "react";
import { MapContainer, Marker, TileLayer, useMap } from "react-leaflet";

export const LOCATION_REGION_LABEL = "Mapa de la ubicación del conductor";
const OSM_ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';
const OSM_TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const MAP_ZOOM = 15;

type LiveLocationMapProps = {
  latitude: number;
  longitude: number;
};

// Keeps the marker centred as new positions arrive without resetting the zoom the viewer chose.
function FollowPosition({ latitude, longitude }: LiveLocationMapProps) {
  const map = useMap();
  useEffect(() => {
    map.panTo([latitude, longitude]);
  }, [map, latitude, longitude]);
  return null;
}

/** Client-only map of the driver's current position. Loaded with next/dynamic and ssr disabled by the container. */
export default function LiveLocationMap({ latitude, longitude }: LiveLocationMapProps) {
  const icon = useMemo(
    () => divIcon({ className: "live-location-marker", html: "<span></span>", iconSize: [18, 18], iconAnchor: [9, 9] }),
    [],
  );

  return (
    <div aria-label={LOCATION_REGION_LABEL} className="live-location-map" role="region">
      <MapContainer
        center={[latitude, longitude]}
        className="live-location-map-canvas"
        scrollWheelZoom={false}
        zoom={MAP_ZOOM}
      >
        <TileLayer attribution={OSM_ATTRIBUTION} url={OSM_TILE_URL} />
        <FollowPosition latitude={latitude} longitude={longitude} />
        <Marker icon={icon} position={[latitude, longitude]} />
      </MapContainer>
    </div>
  );
}
