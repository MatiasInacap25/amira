import csv
from collections.abc import Iterable, Sequence
from io import StringIO

from fastapi import Response

EXPORT_LIMIT = 5_000


def _cell(value: object) -> object:
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def export_csv(filename: str, headers: Sequence[str], rows: Iterable[Sequence[object]]) -> Response:
    output = StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(headers)
    writer.writerows((_cell(cell) for cell in row) for row in rows)
    return Response(
        output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}.csv"', "Cache-Control": "no-store"},
    )
