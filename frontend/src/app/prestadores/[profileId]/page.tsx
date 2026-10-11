import { ProviderProfileView } from "@/components/marketplace/provider-profile-view";

export default async function ProviderProfilePage({ params }: PageProps<"/prestadores/[profileId]">) {
  const { profileId } = await params;
  return <ProviderProfileView profileId={profileId} />;
}
