from django.urls import path

from .views import RagView, SemanticSearchView

urlpatterns = [
    path("ai/semantic-search/", SemanticSearchView.as_view(), name="semantic-search"),
    path("ai/ask/", RagView.as_view(), name="rag-ask"),
]
