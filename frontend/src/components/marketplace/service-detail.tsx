import Link from "next/link";
import type { ReactNode } from "react";
import type { ServiceDetail as ServiceDetailData } from "@/lib/marketplace-api";
import {
  formatServiceAmount,
  formatServiceDate,
  formatServiceDateTime,
  serviceRouteLabel,
  serviceStatusLabel,
} from "@/lib/service-status";

type ServiceDetailProps = {
  service: ServiceDetailData;
  // Provider-only slots, supplied by the container. Each is omitted when the viewer cannot use it.
  actions?: ReactNode;
  assignmentEditor?: ReactNode;
  deliveryPhoto?: ReactNode;
  // Customer-only slot: claim window, consent and claim actions.
  customerResolution?: ReactNode;
};

const NO_VALUE_LABEL = "No indicado";

/** Body of a service. The viewer's role decides how the other party is labelled. */
export function ServiceDetail({ service, actions, assignmentEditor, deliveryPhoto, customerResolution }: ServiceDetailProps) {
  const counterpartLabel = service.viewerRole === "customer" ? "Prestador" : "Cliente";
  return (
    <article aria-labelledby="account-service-detail-title" className="account-service-detail">
      <header className="account-service-detail-heading">
        <div>
          <p className="account-service-meta">{counterpartLabel}: {service.counterpartName}</p>
          <h1 id="account-service-detail-title">{service.serviceTypeName}</h1>
        </div>
        <span className={`account-service-status account-service-status-${service.status}`}>{serviceStatusLabel(service.status)}</span>
      </header>

      <dl className="account-service-detail-facts">
        <div>
          <dt>Ruta</dt>
          <dd>{serviceRouteLabel(service.originCommune, service.destinationCommune)}</dd>
        </div>
        <div>
          <dt>Fecha del servicio</dt>
          <dd>{formatServiceDateTime(service.serviceAt)}</dd>
        </div>
        <div>
          <dt>Monto</dt>
          <dd>{formatServiceAmount(service.amount)}</dd>
        </div>
        <div>
          <dt>Exclusivo</dt>
          <dd>{service.isExclusive ? "Sí" : "No"}</dd>
        </div>
        <div>
          <dt>Creado</dt>
          <dd>{formatServiceDate(service.createdAt)}</dd>
        </div>
        <div>
          <dt>Iniciado</dt>
          <dd>{formatServiceDateTime(service.startedAt)}</dd>
        </div>
        <div>
          <dt>Finalizado</dt>
          <dd>{formatServiceDateTime(service.completedAt)}</dd>
        </div>
        <div>
          <dt>Plazo de pago</dt>
          <dd>{formatServiceDateTime(service.payoutDeadlineAt)}</dd>
        </div>
      </dl>

      {service.description && (
        <section aria-labelledby="account-service-description-title" className="account-service-section">
          <h2 id="account-service-description-title">Descripción</h2>
          <p className="account-service-description">{service.description}</p>
        </section>
      )}

      <section aria-labelledby="account-service-assignments-title" className="account-service-section">
        <h2 id="account-service-assignments-title">Conductores asignados</h2>
        {assignmentEditor ?? (
          service.assignments.length === 0 ? (
            <p className="account-service-empty">Aún no hay conductores asignados</p>
          ) : (
            <ul className="account-service-assignments">
              {service.assignments.map((assignment) => (
                <li key={`${assignment.driverId}-${assignment.vehicleId}`}>
                  <strong>{assignment.driverFirstName || NO_VALUE_LABEL}</strong>
                  <span>{assignment.vehicleLabel || NO_VALUE_LABEL}</span>
                  <span className="account-service-plate">{assignment.plate || NO_VALUE_LABEL}</span>
                </li>
              ))}
            </ul>
          )
        )}
      </section>

      {actions && (
        <section aria-labelledby="account-service-actions-title" className="account-service-section">
          <h2 id="account-service-actions-title">Acciones</h2>
          {actions}
        </section>
      )}

      {deliveryPhoto && (
        <section aria-labelledby="account-service-photo-title" className="account-service-section">
          <h2 id="account-service-photo-title">Foto de entrega</h2>
          {deliveryPhoto}
        </section>
      )}

      {customerResolution && (
        <section aria-labelledby="account-service-resolution-title" className="account-service-section">
          <h2 id="account-service-resolution-title">Conformidad y reclamo</h2>
          {customerResolution}
        </section>
      )}

      {service.chatId && (
        <Link className="button button-secondary account-service-chat" href={`/mensajes/${encodeURIComponent(service.chatId)}`}>
          Abrir conversación
        </Link>
      )}
    </article>
  );
}
