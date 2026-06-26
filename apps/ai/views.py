from rest_framework.response import Response
from rest_framework.views import APIView

from django.conf import settings

from apps.accounts.permissions import IsTenantMember
from apps.analytics.tracking import log_ai_interaction, track

from .rag import rag_answer, semantic_search


class SemanticSearchView(APIView):
    permission_classes = [IsTenantMember]
    throttle_scope = "search"

    def get(self, request):
        q = request.query_params.get("q", "").strip()
        if not q:
            return Response({"detail": "q required"}, status=400)
        results = semantic_search(q)
        track(request, "search", query=q[:500], result_count=len(results))
        return Response({"results": results})


class RagView(APIView):
    permission_classes = [IsTenantMember]
    throttle_scope = "search"

    def get(self, request):
        q = request.query_params.get("q", "").strip()
        if not q:
            return Response({"detail": "q required"}, status=400)
        answer = rag_answer(q)
        usable = sum(1 for s in answer["sources"] if s["score"] > 0)
        track(request, "search", query=q[:500], result_count=usable)
        answer["interaction_id"] = log_ai_interaction(
            request, q, answer["answer"], answer["sources"],
            model_name=getattr(settings, "AI_GEN_MODEL", ""),
        )
        return Response(answer)
