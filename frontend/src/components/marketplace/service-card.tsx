import Link from "next/link";
import type { ServiceListItem } from "@/lib/marketplace-api";
import { formatServiceAmount, formatServiceDate, serviceRouteLabel, serviceStatusLabel } from "@/lib/service-status";

type ServiceCardProps = {
  service: ServiceListItem;
  /** Role-specific label for the other party, e.g. "Cliente" for providers. */
  counterpartLabel: string;
};

/** One row in the "Mis servicios" list. Presentational only: the parent supplies the data. */
export function ServiceCard({ service, counterpartLabel }: ServiceCardProps) {
  const titleId = `account-service-${service.serviceId}-title`;
  return (
    <article aria-labelledby={titleId} className="account-service-card">
      <div className="account-service-card-heading">
        <div>
          <h2 id={titleId}>
            <Link className="account-service-card-link" href={`/cuenta/servicios/${encodeURIComponent(service.serviceId)}`}>
              {service.serviceTypeName}
            </Link>
          </h2>
          <p className="account-service-meta">{counterpartLabel}: {service.counterpartName}</p>
        </div>
        <span className={`account-service-status account-service-status-${service.status}`}>{serviceStatusLabel(service.status)}</span>
      </div>
      <dl className="account-service-facts">
        <div>
          <dt>Ruta</dt>
          <dd>{serviceRouteLabel(service.originCommune, service.destinationCommune)}</dd>
        </div>
        <div>
          <dt>Fecha</dt>
          <dd>{formatServiceDate(service.serviceAt)}</dd>
        </div>
        <div>
          <dt>Monto</dt>
          <dd>{formatServiceAmount(service.amount)}</dd>
        </div>
        <div>
          <dt>Conductores</dt>
          <dd>{service.assignmentCount}</dd>
        </div>
      </dl>
      {service.isExclusive && <p className="account-service-exclusive">Servicio exclusivo</p>}
    </article>
  );
}
