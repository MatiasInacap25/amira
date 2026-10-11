import { ServiceDetailView } from "@/components/marketplace/service-detail-view";

export default async function ServiceDetailPage({ params }: { params: Promise<{ serviceId: string }> }) {
  const { serviceId } = await params;
  return <ServiceDetailView serviceId={serviceId} />;
}
