from django.urls import path
from . import views

app_name = "naukri"

urlpatterns = [
    path("", views.index, name="index"),
    path("job/<str:job_id>/", views.job_detail, name="job_detail"),
    path("export/csv/", views.export_csv, name="export_csv"),
]
