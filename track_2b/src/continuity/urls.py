from django.urls import include, path
from identity import views

urlpatterns = [
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
