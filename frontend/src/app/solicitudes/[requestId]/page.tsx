import { ProviderRequestDetail } from "@/components/marketplace/provider-request-detail";

export default async function ProviderRequestDetailPage({ params }: { params: Promise<{ requestId: string }> }) {
  const { requestId } = await params;
  return <ProviderRequestDetail requestId={requestId} />;
}
