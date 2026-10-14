from django.urls import include, path
from identity import views
from records import continuity_views as cv
from identity import profile_views as pv
from records import medication_views as mv
from identity import frontend_views as fv

urlpatterns = [
    path('api/session/', fv.session, name='frontend_session'),
    path('app/', fv.shell, name='comfort_frontend'),
    path('app/<path:route>', fv.shell),
    path('profile/',pv.my_profile,name='my_profile'),
    path('medications/',mv.my_medications,name='my_medications'),
    path('workspaces/<uuid:workspace_id>/profile/',pv.profile_page,name='patient_profile'),
    path('workspaces/<uuid:workspace_id>/medications/',mv.page,name='patient_medications'),
    path('received/',cv.received_page,name='received_access'),
    path('api/continuity/account/',cv.account,name='comfort_account'),
    path('api/continuity/received/',cv.received,name='received_grants'),
    path('api/continuity/shares/<uuid:grant_id>/',cv.shared_packet,name='shared_packet'),
    path('api/continuity/shares/<uuid:grant_id>/versions/<uuid:version_id>/original/',cv.shared_original,name='shared_original'),
    path('api/continuity/contribution-authorities/<uuid:grant_id>/submit/',cv.submit_contribution,name='submit_contribution'),
    path('api/workspaces/<uuid:workspace_id>/', include('records.urls')),
    path('', views.landing, name='landing'),
    path('auth/login/', views.oidc_login, name='oidc_login'),
    path('auth/callback/', views.oidc_callback, name='oidc_callback'),
    path('auth/logout/', views.sign_out, name='sign_out'),
    path('auth/logged-out/', views.logged_out, name='logged_out'),
    path('workspaces/', views.workspace_list, name='workspace_list'),
    path('workspaces/<uuid:workspace_id>/', views.workspace_home, name='workspace_home'),
    path('health/', views.health, name='health'),
]
