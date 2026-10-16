from django.urls import path
from . import views
from . import continuity_views as cv
from identity import profile_views as pv
from . import medication_views as mv
from . import care_views as care
from . import journal_views as journal
from . import insights_views as insights

urlpatterns=[
    path('insights/timeline/',insights.timeline,name='insights_timeline'),
    path('insights/observations/',insights.observations,name='insights_observations'),
    path('journal/',journal.entries,name='journal_entries'),
    path('journal/draft/',journal.draft,name='journal_draft'),
    path('journal/draft/discard/',journal.discard,name='journal_draft_discard'),
    path('journal/ai/requests/',journal.ai_requests,name='journal_ai_requests'),
    path('journal/ai/requests/<uuid:request_id>/',journal.ai_request,name='journal_ai_request'),
    path('journal/<uuid:event_id>/',journal.entry,name='journal_entry'),
    path('journal/<uuid:event_id>/status/',journal.status,name='journal_status'),
    path('journal/<uuid:event_id>/history/',journal.history,name='journal_history'),
    path('care/<str:kind>/',care.entries,name='care_entries'),
    path('care/<str:kind>/<uuid:item_id>/',care.entry,name='care_entry'),
    path('care/<str:kind>/<uuid:item_id>/status/',care.status,name='care_entry_status'),
    path('care/<str:kind>/<uuid:item_id>/history/',care.history,name='care_entry_history'),
    path('profile/',pv.profile,name='profile_api'),
    path('care-circle/',pv.contacts,name='care_circle'),
    path('care-circle/<uuid:contact_id>/',pv.contact,name='care_circle_contact'),
    path('care-circle/<uuid:contact_id>/status/',pv.contact_state,name='care_circle_status'),
    path('care-circle/resolve/',pv.resolve_contact,name='care_circle_resolve'),
    path('care-circle/choices/',pv.circle_choices,name='care_circle_choices'),
    path('medications/',mv.entries,name='medication_entries'),
    path('medications/choices/',mv.choices,name='medication_choices'),
    path('medications/<uuid:entry_id>/',mv.entry,name='medication_entry'),
    path('medications/<uuid:entry_id>/status/',mv.status,name='medication_status'),
    path('episodes/',cv.episodes,name='episodes'),
    path('episodes/<uuid:episode_id>/sources/',cv.episode_sources,name='episode_sources'),
    path('recipients/resolve/',cv.resolve_recipient,name='resolve_recipient'),
    path('grants/',cv.grants,name='patient_grants'),
    path('grants/<str:kind>/<uuid:grant_id>/revoke/',cv.revoke_grant,name='revoke_grant'),
    path('contributions/',cv.inbox,name='contribution_inbox'),
    path('contributions/<uuid:contribution_id>/original/',cv.contribution_original,name='contribution_original'),
    path('contributions/<uuid:contribution_id>/review/',cv.review_contribution,name='review_contribution'),
    path('facilities/search/',views.facilities,name='facility_search'),
    path('records/',views.records,name='records'),
    path('records/search/',views.records_search,name='records_search'),
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
