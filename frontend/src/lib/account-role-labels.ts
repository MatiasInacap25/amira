const ROLE_LABELS: Record<string, string> = {
  client: "Cliente",
  independent_driver: "Conductor independiente",
  company_owner: "Dueño de empresa",
  company_driver: "Conductor de empresa",
};

const UNASSIGNED_ROLE_LABEL = "Cuenta sin rol asignado";

// Maps a backend account role code to its Spanish label. Unknown or missing roles get a neutral fallback.
export function accountRoleLabel(role: string | null | undefined): string {
  if (!role) return UNASSIGNED_ROLE_LABEL;
  return Object.hasOwn(ROLE_LABELS, role) ? ROLE_LABELS[role] : UNASSIGNED_ROLE_LABEL;
}
