from django.urls import path
from . import views, api
from .api import worker_by_badge
from django.urls import path
from . import views


urlpatterns = [
    path('', views.login_page, name='login'),
    path('select-station/', views.station_picker, name='station_picker'),
    path('select-station/clear/', views.station_picker_clear, name='station_picker_clear'),
    path('dashboard/', views.production_dashboard, name='production_dashboard'),
    path('run/', views.run_page, name='run_page'),
    path('station/<slug:station_slug>/', views.station_detail, name='station_detail'),
    path("api/worker/<str:badge>/", worker_by_badge),
    path("warehouse/", views.warehouse_dashboard, name="warehouse"),
    path("api/reorder/", api.create_reorder),
    path("", views.login_page, name="login"),
    path("warehouse/", views.warehouse_dashboard, name="warehouse"),
    path("orders/create/", views.create_production_order),
    path("orders/", views.orders_page),
    path("orders/delete/<int:id>/", views.delete_order),
    # ... ваши другие пути ...
    path('api/station/<slug:station_slug>/start-truck/', api.start_truck_api, name='api_start_truck'),
    # API Endpoints
    path('api/dashboard/', api.dashboard_api, name='api_dashboard'),
    path('api/station/<slug:station_slug>/data/', api.station_data_api, name='api_station_data'),
    path('api/station/<slug:station_slug>/next-task/', api.next_task_api, name='api_next_task'),
    path('api/station/<slug:station_slug>/take-over/', api.take_over_task_api, name='api_take_over'),
    path('api/station/<slug:station_slug>/reset/', api.reset_truck_api, name='api_reset'),
    path('api/station/<slug:station_slug>/select/', api.select_task_api, name='api_select'),
]