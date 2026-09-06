from django.urls import path

from .views import RagView

urlpatterns = [
    path("ai/ask/", RagView.as_view(), name="rag-ask"),
]
