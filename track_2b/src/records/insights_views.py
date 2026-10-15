from django.http import JsonResponse
from django.views.decorators.http import require_GET
from . import insights
from .continuity_views import checked


@require_GET
@checked
def timeline(request,workspace_id):
    return JsonResponse(insights.timeline(request.user,workspace_id,request.GET))


@require_GET
@checked
def observations(request,workspace_id):
    return JsonResponse(insights.observations(request.user,workspace_id,request.GET))
