"use client";

import { useQuery } from "@tanstack/react-query";
import { getLocations } from "@/lib/marketplace-api";

export type RegionCommuneValue = {
  regionCode: string;
  communeCode: string;
};

type Props = {
  idPrefix: string;
  value: RegionCommuneValue;
  onChange: (value: RegionCommuneValue) => void;
  required?: boolean;
  optional?: boolean;
  regionLabel?: string;
  communeLabel?: string;
};

const LOCATIONS_STALE_TIME = 60 * 60 * 1000;

export function RegionCommuneSelect({
  idPrefix,
  value,
  onChange,
  required = false,
  optional = false,
  regionLabel = "Región",
  communeLabel = "Comuna",
}: Props) {
  const locationsQuery = useQuery({
    queryKey: ["locations"],
    queryFn: ({ signal }) => getLocations(signal),
    retry: false,
    staleTime: LOCATIONS_STALE_TIME,
  });

  const regions = locationsQuery.data?.regions ?? [];
  const selectedRegion = regions.find((region) => region.code === value.regionCode);
  const communes = selectedRegion?.communes ?? [];
  const regionId = `${idPrefix}-region`;
  const communeId = `${idPrefix}-commune`;
  const catalogUnavailable = locationsQuery.isError;

  return (
    <>
      <label className="marketplace-field" htmlFor={regionId}>
        <span>{regionLabel}</span>
        <select
          disabled={locationsQuery.isPending || catalogUnavailable}
          id={regionId}
          onChange={(event) => onChange({ regionCode: event.target.value, communeCode: "" })}
          required={required}
          value={value.regionCode}
        >
          <option value="">{optional ? "Todas las regiones" : "Elige una región"}</option>
          {regions.map((region) => <option key={region.code} value={region.code}>{region.name}</option>)}
        </select>
      </label>
      <label className="marketplace-field" htmlFor={communeId}>
        <span>{communeLabel}</span>
        <select
          disabled={!selectedRegion}
          id={communeId}
          onChange={(event) => onChange({ regionCode: value.regionCode, communeCode: event.target.value })}
          required={required}
          value={value.communeCode}
        >
          <option value="">{optional ? "Todas las comunas" : "Elige una comuna"}</option>
          {communes.map((commune) => <option key={commune.code} value={commune.code}>{commune.name}</option>)}
        </select>
      </label>
      {locationsQuery.isPending && <p className="marketplace-field-status">Cargando regiones y comunas…</p>}
      {catalogUnavailable && <p className="marketplace-field-status marketplace-field-error" role="alert">No pudimos cargar las regiones y comunas. Inténtalo nuevamente más tarde.</p>}
    </>
  );
}
