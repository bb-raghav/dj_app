# todo/urls.py
from django.urls import path
from . import views

urlpatterns = [
    # Page routes
    path("", views.index, name="index"),
    path("login/", views.login_page, name="login_page"),
    path("signup/", views.signup_page, name="signup_page"),
    path("home/", views.home, name="home"),
    # API routes
    path("api/user/", views.get_user, name="api_user"),
    path("api/signup/", views.api_signup, name="api_signup"),
    path("api/login/", views.api_login, name="api_login"),
    path("api/logout/", views.api_logout, name="api_logout"),
    path("api/tasks/", views.api_tasks, name="api_tasks"),
    path("api/add/", views.add_task, name="add_task"),
    path("edit/<int:task_id>/", views.edit_task, name="edit_task"),
    path("delete/<int:task_id>/", views.delete_task, name="delete_task"),
    path(
        "toggle_complete/<int:task_id>/", views.toggle_complete, name="toggle_complete"
    ),
    path("api/cache_stats/", views.cache_stats, name="api_cache_stats"),
    path("api/telemetry/", views.telemetry, name="api_telemetry"),
]
