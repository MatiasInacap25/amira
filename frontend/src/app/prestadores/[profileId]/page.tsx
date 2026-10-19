import { ProviderProfileView } from "@/components/marketplace/provider-profile-view";

function decodeRouteParam(value: string) {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}

export default async function ProviderProfilePage({ params }: PageProps<"/prestadores/[profileId]">) {
  const { profileId } = await params;
  return <ProviderProfileView profileId={decodeRouteParam(profileId)} />;
}
