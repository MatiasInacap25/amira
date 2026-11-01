"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { getLocations, getServiceTypes } from "@/lib/marketplace-api";
import {
  missingProfileLabels,
  profileMutationErrorMessage,
  publishProviderProfile,
  requestProviderProfile,
  saveProviderProfile,
  unpublishProviderProfile,
  type ProviderProfile,
  type ProviderProfileInput,
  type ProviderProfileMissingItem,
} from "@/lib/provider-profile-api";
import { accountAccessMessage, currentAccessToken, ProviderRequestAccessError } from "@/lib/provider-request-access";

export const PROVIDER_PROFILE_QUERY_KEY = ["provider-profile"];

const CATALOG_STALE_TIME = 60 * 60 * 1000;
const AUTO_UNPUBLISHED_MESSAGE = "Tu perfil dejó de ser público porque le faltan datos.";

type Props = {
  isCompany: boolean;
};

// Owner-only editor for the public provider profile. The parent renders it only for provider roles.
export function ProviderProfileForm({ isCompany }: Props) {
  const profileQuery = useQuery({
    queryKey: PROVIDER_PROFILE_QUERY_KEY,
    queryFn: async ({ signal }) => requestProviderProfile(await currentAccessToken(), signal),
    retry: false,
    staleTime: 60_000,
  });

  if (profileQuery.isPending) return <p role="status">Cargando tu perfil de proveedor…</p>;

  // Full error screens only when no profile is loaded yet; a failed background refetch must not discard unsaved edits.
  if (!profileQuery.data) {
    if (profileQuery.error instanceof ProviderRequestAccessError) {
      return <p role="alert">{accountAccessMessage(profileQuery.error.reason, "profile")}</p>;
    }

    return (
      <div className="marketplace-state marketplace-error" role="alert">
        <p>No pudimos cargar tu perfil de proveedor. Inténtalo nuevamente.</p>
        <button className="button button-secondary" onClick={() => void profileQuery.refetch()} type="button">Reintentar</button>
      </div>
    );
  }

  return (
    <>
      {profileQuery.isError && (
        <p className="marketplace-field-error" role="alert">No pudimos actualizar tu perfil. Tus cambios sin guardar se mantienen.</p>
      )}
      <ProviderProfileFields isCompany={isCompany} profile={profileQuery.data} />
    </>
  );
}

type FieldsProps = {
  isCompany: boolean;
  profile: ProviderProfile;
};

// Mirrors the backend's publish rules on the form values, so the checklist and the publish gate follow what the user sees.
function formMissingItems(values: {
  description: string;
  communeCode: string;
  serviceTypeIds: string[];
  name: string;
  isCompany: boolean;
}): ProviderProfileMissingItem[] {
  const missing: ProviderProfileMissingItem[] = [];
  if (!values.description.trim()) missing.push("description");
  if (!values.communeCode) missing.push("commune");
  if (values.serviceTypeIds.length === 0) missing.push("service_types");
  if (values.isCompany && !values.name.trim()) missing.push("name");
  return missing;
}

function ProviderProfileFields({ isCompany, profile }: FieldsProps) {
  const queryClient = useQueryClient();
  // Form values start from the server profile and then belong to the user until they save or publish.
  const [description, setDescription] = useState(profile.description ?? "");
  const [name, setName] = useState(profile.name);
  const [communeCode, setCommuneCode] = useState(profile.commune_code ?? "");
  const [serviceTypeIds, setServiceTypeIds] = useState(profile.service_type_ids);
  const [autoUnpublished, setAutoUnpublished] = useState(false);

  const locationsQuery = useQuery({
    queryKey: ["locations"],
    queryFn: ({ signal }) => getLocations(signal),
    retry: false,
    staleTime: CATALOG_STALE_TIME,
  });
  const serviceTypesQuery = useQuery({
    queryKey: ["service-types"],
    queryFn: ({ signal }) => getServiceTypes(signal),
    retry: false,
    staleTime: CATALOG_STALE_TIME,
  });

  const refreshProfile = () => queryClient.invalidateQueries({ queryKey: PROVIDER_PROFILE_QUERY_KEY });

  const saveMutation = useMutation({
    mutationFn: async (input: ProviderProfileInput) => saveProviderProfile(await currentAccessToken(), input),
    onSuccess: refreshProfile,
  });
  // Publish saves the form first, so it publishes what the user sees; if the save fails, nothing is published.
  const publishMutation = useMutation({
    mutationFn: async (input: ProviderProfileInput) => {
      const token = await currentAccessToken();
      await saveProviderProfile(token, input);
      // The save already stored the profile, so refresh it even when the publish below fails.
      try {
        return await publishProviderProfile(token);
      } finally {
        void refreshProfile();
      }
    },
  });
  const unpublishMutation = useMutation({
    mutationFn: async () => unpublishProviderProfile(await currentAccessToken()),
    onSuccess: refreshProfile,
  });

  const regions = locationsQuery.data?.regions ?? [];
  const serviceTypes = serviceTypesQuery.data?.items ?? [];
  const catalogsUnavailable = locationsQuery.isError || serviceTypesQuery.isError;
  const formValues = { description, communeCode, serviceTypeIds, name, isCompany };
  const missing = formMissingItems(formValues);
  const checklist = missingProfileLabels(missing);
  const pendingAction = saveMutation.isPending || publishMutation.isPending || unpublishMutation.isPending;
  const publishDisabled = pendingAction || (!profile.published && missing.length > 0);
  const actionError = saveMutation.error ?? publishMutation.error ?? unpublishMutation.error;

  function currentInput(): ProviderProfileInput {
    return {
      description,
      commune_code: communeCode || null,
      service_type_ids: serviceTypeIds,
      ...(isCompany ? { name } : {}),
    };
  }

  // Each action resets the others so only the latest outcome is shown.
  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    publishMutation.reset();
    unpublishMutation.reset();
    saveMutation.mutate(currentInput(), {
      onSuccess: (saved) => setAutoUnpublished(profile.published && !saved.published),
    });
  }

  function runPublishAction() {
    saveMutation.reset();
    setAutoUnpublished(false);
    if (profile.published) {
      unpublishMutation.reset();
      unpublishMutation.mutate();
    } else {
      publishMutation.reset();
      publishMutation.mutate(currentInput());
    }
  }

  function toggleServiceType(serviceTypeId: string, checked: boolean) {
    setServiceTypeIds((current) => (checked ? [...current, serviceTypeId] : current.filter((id) => id !== serviceTypeId)));
  }

  return (
    <section className="provider-profile-form" aria-labelledby="provider-profile-heading">
      <h2 id="provider-profile-heading">Perfil público</h2>
      <p className="provider-profile-status" role="status">
        {profile.published ? "Tu perfil está publicado y aparece cuando un usuario busca un servicio." : "Tu perfil no está publicado."}
      </p>
      {autoUnpublished && !profile.published && <p className="marketplace-field-error" role="status">{AUTO_UNPUBLISHED_MESSAGE}</p>}

      {checklist.length > 0 && (
        <div>
          <p className="provider-profile-checklist-title">Falta para publicar tu perfil:</p>
          <ul className="provider-profile-checklist">
            {checklist.map((label) => <li key={label}>{label}</li>)}
          </ul>
        </div>
      )}

      {catalogsUnavailable && (
        <p className="marketplace-field-error" role="alert">No pudimos cargar las comunas y los tipos de servicio. Inténtalo nuevamente más tarde.</p>
      )}

      <form className="provider-profile-fields" onSubmit={handleSubmit}>
        {isCompany && (
          <label className="marketplace-field" htmlFor="provider-profile-name">
            <span>Nombre de la empresa</span>
            <input id="provider-profile-name" onChange={(event) => setName(event.target.value)} type="text" value={name} />
          </label>
        )}

        <label className="marketplace-field" htmlFor="provider-profile-description">
          <span>Descripción</span>
          <textarea
            id="provider-profile-description"
            onChange={(event) => setDescription(event.target.value)}
            rows={4}
            value={description}
          />
        </label>

        <label className="marketplace-field" htmlFor="provider-profile-commune">
          <span>Comuna</span>
          <select
            disabled={locationsQuery.isPending || locationsQuery.isError}
            id="provider-profile-commune"
            onChange={(event) => setCommuneCode(event.target.value)}
            value={communeCode}
          >
            <option value="">Elige una comuna</option>
            {regions.map((region) => (
              <optgroup key={region.code} label={region.name}>
                {region.communes.map((commune) => <option key={commune.code} value={commune.code}>{commune.name}</option>)}
              </optgroup>
            ))}
          </select>
        </label>

        <fieldset className="provider-profile-fieldset" disabled={serviceTypesQuery.isPending || serviceTypesQuery.isError}>
          <legend>Tipos de servicio</legend>
          <div className="provider-profile-services">
            {serviceTypes.map((serviceType) => (
              <label className="provider-profile-checkbox" htmlFor={`provider-profile-service-${serviceType.id}`} key={serviceType.id}>
                <input
                  checked={serviceTypeIds.includes(serviceType.id)}
                  id={`provider-profile-service-${serviceType.id}`}
                  onChange={(event) => toggleServiceType(serviceType.id, event.target.checked)}
                  type="checkbox"
                />
                <span>{serviceType.name}</span>
              </label>
            ))}
          </div>
        </fieldset>

        <div className="provider-profile-actions">
          <button className="button button-primary" disabled={pendingAction} type="submit">
            {saveMutation.isPending ? "Guardando…" : "Guardar"}
          </button>
          <button className="button button-secondary" disabled={publishDisabled} onClick={runPublishAction} type="button">
            {profile.published ? "Ocultar perfil" : "Publicar perfil"}
          </button>
        </div>
      </form>

      {saveMutation.isSuccess && !pendingAction && <p role="status">Cambios guardados.</p>}
      {actionError && (
        <p className="marketplace-field-error" role="alert">
          {profileMutationErrorMessage(actionError)}
        </p>
      )}
    </section>
  );
}
