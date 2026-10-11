"""Command-line entry point for the payout release job: ``python -m amira_api.release_payouts``.

This module is the composition root for the payout port; the domain in payout_service.py never chooses an adapter.
The process exits 0 when the run completes, including when single services failed (they are logged and stay due for
the next run). It exits 1 when the job cannot run at all: the payout adapter is refused for this APP_ENV, DATABASE_URL
is not configured, or an unexpected error escapes the run.
"""

import logging
import sys
from dataclasses import asdict

from sqlalchemy.orm import Session

from amira_api.clock import utc_now
from amira_api.db import get_engine
from amira_api.payout_provider import PayoutProvider
from amira_api.payout_service import release_due_payouts
from amira_api.settings import Settings, get_settings
from amira_api.simulated_payout_provider import SimulatedPayoutProvider

logger = logging.getLogger("amira_api.release_payouts")


def build_payout_provider(settings: Settings) -> PayoutProvider:
    """Only the simulated adapter exists. APP_ENV must be set explicitly, mirroring the payment composition root."""
    if "app_env" not in settings.model_fields_set:
        raise RuntimeError("Payout release requires APP_ENV to be set explicitly.")
    return SimulatedPayoutProvider(app_env=settings.app_env)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        provider = build_payout_provider(get_settings())
        engine = get_engine()
    except RuntimeError as error:
        logger.error("Payout release cannot run: %s", error)
        return 1

    with Session(engine) as session:
        summary = release_due_payouts(session, utc_now(), provider)
    logger.info("Payout release finished: %s", asdict(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
