"""CSV export — analysts live in spreadsheets. Stdlib csv, no new dependency."""
import csv

from django.http import HttpResponse


def csv_response(filename, header, rows):
    """rows = iterable of sequences matching `header`."""
    resp = HttpResponse(content_type="text/csv")
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    writer = csv.writer(resp)
    writer.writerow(header)
    writer.writerows(rows)
    return resp


def case_reports_csv(reports):
    header = [
        "id", "created_at", "disease", "severity", "outcome",
        "age_group", "sex", "region", "reporter",
    ]
    rows = (
        reports.select_related("disease", "reporter").values_list(
            "id", "created_at", "disease__name", "severity", "outcome",
            "patient_age_group", "patient_sex", "region", "reporter__username",
        )
    )
    return csv_response("case_reports.csv", header, rows)
