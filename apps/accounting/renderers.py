"""Renderers used by accounting list and export endpoints."""

import csv
import io
import json

from rest_framework.renderers import BaseRenderer


class CSVRenderer(BaseRenderer):
    """Render a sequence of flat mappings as a UTF-8 CSV download."""

    media_type = "text/csv"
    format = "csv"
    charset = "utf-8"

    def render(self, data, accepted_media_type=None, renderer_context=None):
        response = (renderer_context or {}).get("response")
        view = (renderer_context or {}).get("view")
        filename = getattr(view, "csv_filename", "export")
        if response is not None:
            response["Content-Disposition"] = f'attachment; filename="{filename}.csv"'

        rows = data if isinstance(data, list) else []
        fieldnames = list(rows[0].keys()) if rows else []
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
        if fieldnames:
            writer.writeheader()
            for row in rows:
                writer.writerow(
                    {
                        key: json.dumps(value, ensure_ascii=False, default=str)
                        if isinstance(value, (dict, list))
                        else value
                        for key, value in row.items()
                    }
                )
        return output.getvalue()
