from django.urls import path
from . import views

urlpatterns=[
    path('facilities/search/',views.facilities,name='facility_search'),
    path('records/',views.records,name='records'),
    path('records/<uuid:record_id>/',views.record,name='record'),
    path('records/<uuid:record_id>/versions/',views.new_version,name='source_version_create'),
    path('records/<uuid:record_id>/review/',views.review,name='metadata_review'),
    path('versions/<uuid:version_id>/original/',views.original,name='source_original'),
    path('versions/<uuid:version_id>/image/',views.image_details,name='source_image_details'),
    path('versions/<uuid:version_id>/preview/',views.image_preview,name='source_image_preview'),
    path('jobs/<uuid:job_id>/retry/',views.retry,name='ingestion_retry'),
    path('packets/',views.packets,name='packets'),
    path('packets/<uuid:packet_id>/',views.packet,name='packet'),
    path('assistant/tasks/',views.assistant_tasks,name='assistant_tasks'),
    path('assistant/status/',views.assistant_status,name='assistant_status'),
    path('assistant/tasks/<uuid:task_id>/',views.assistant_task,name='assistant_task'),
    path('assistant/tasks/<uuid:task_id>/cancel/',views.assistant_cancel,name='assistant_cancel'),
]
