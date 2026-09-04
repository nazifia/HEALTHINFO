"""Page-number pagination a client may ask for a smaller page of.

Plain PageNumberPagination ignores ``?page_size=``, so the typeahead lookups
(the dispensing counter's patient box, the patient picker) were asking for the
first few matches and being handed a full 25-row page to throw away.
"""
from rest_framework.pagination import PageNumberPagination


class SizedPageNumberPagination(PageNumberPagination):
    page_size_query_param = "page_size"
    max_page_size = 100
