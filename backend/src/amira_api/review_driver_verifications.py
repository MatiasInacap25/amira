"""Command line for the manual review of driver certificates: ``python -m amira_api.review_driver_verifications``.

    list                         certificates in review, with the holder, RUT, folio and annotations
    approve <id>                 mark a certificate in review as verified
    reject <id> --reason "..."   reject it; the driver sees the reason and can submit another certificate

Run by an Amira administrator with the backend's DATABASE_URL; it is not exposed over HTTP. Exit codes: 0 done,
1 the job cannot run (no database), 2 the request was refused (bad arguments, unknown id, not in review).
"""

import argparse
import sys
from uuid import UUID

from sqlalchemy.orm import Session

from amira_api.clock import utc_now
from amira_api.db import get_engine
from amira_api.driver_verification_review import ReviewRefused, approve_certificate, pending_reviews, reject_certificate

DOCUMENT_LABELS = {"criminal_record": "Certificado de antecedentes", "driver_record": "Hoja de vida del conductor"}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m amira_api.review_driver_verifications")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="certificados en revisión")
    approve = commands.add_parser("approve", help="aprobar un certificado en revisión")
    approve.add_argument("certificate_id", type=UUID)
    reject = commands.add_parser("reject", help="rechazar un certificado en revisión")
    reject.add_argument("certificate_id", type=UUID)
    reject.add_argument("--reason", required=True, help="motivo que verá el conductor")
    return parser


def _print_pending(session: Session) -> None:
    pending = pending_reviews(session)
    if not pending:
        print("No hay certificados en revisión.")
        return
    for item in pending:
        print(f"{item.id}  {DOCUMENT_LABELS.get(item.document_type or '', item.document_type)}")
        print(f"  Titular: {item.holder} (RUT {item.rut or 'sin RUT'})  Folio: {item.folio}  Enviado: {item.submitted_at:%Y-%m-%d %H:%M}")
        for register in item.annotations:
            print(f"  - {register.get('register', '?')}: {register.get('fines', '?')}")
        if item.pdf_storage_key:
            print(f"  PDF: {item.pdf_storage_key}")


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        engine = get_engine()
    except RuntimeError as error:
        print(f"La revisión no puede ejecutarse: {error}", file=sys.stderr)
        return 1
    with Session(engine) as session:
        try:
            if args.command == "list":
                _print_pending(session)
            elif args.command == "approve":
                approve_certificate(session, args.certificate_id, utc_now())
                print(f"Certificado {args.certificate_id} aprobado.")
            else:
                reject_certificate(session, args.certificate_id, args.reason, utc_now())
                print(f"Certificado {args.certificate_id} rechazado.")
        except ReviewRefused as refused:
            print(str(refused), file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
