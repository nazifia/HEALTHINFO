"""The search backend every list uses (see REST_FRAMEWORK in settings)."""
import re

from rest_framework import filters

from apps.patients.models import number_search_term

# A query that is nothing but digits and the separators people type into a
# phone number: "0803 123 4567", "+234-803-123-4567", "(0803)1234567".
# ponytail: global default, so a dashed digit-only code ("12-345") is folded
# too. Give that list its own SearchFilter if one ever exists.
_NUMBER_QUERY = re.compile(r"[+(]?\d[\d\s()+-]{4,}")


class NumberAwareSearchFilter(filters.SearchFilter):
    """SearchFilter that folds a typed number onto the shape we store.

    Without it "+2348031234567" and "0803-123-4567" match nothing, and the
    default term split turns a spaced number into three fragments that match
    by luck rather than by number.
    """

    def get_search_terms(self, request):
        raw = request.query_params.get(self.search_param, "").strip()
        if _NUMBER_QUERY.fullmatch(raw):
            return [number_search_term(raw)]
        return super().get_search_terms(request)
