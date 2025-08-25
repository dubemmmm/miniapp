from django.urls import path
from . import views

urlpatterns = [
    path('', views.landing_view, name='landing'),
    path('home', views.home, name='home'),
    path('api/sync-airtable/', views.sync_airtable, name='sync_airtable'),
    path('admins/create-employee/', views.create_employee_view, name='create_employee'),
    path('api/properties/', views.properties_api, name='properties_api'),
    path('api/properties/<int:property_id>/', views.property_detail_api, name='property_detail_api'),
    path('api/create-shared-list/', views.create_shared_list, name='create_shared_list'),
    path('property/<int:property_id>/pdf/', views.download_property_pdf, name='property_pdf'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('manage-shares/', views.manage_shared_lists, name='manage_shared_lists'),
    path('api/compare-properties/', views.compare_properties, name='compare_properties'),
    path('api/comparison-properties/<str:property_ids>/', views.comparison_pdf, name='comparison_pdf'),
    path('shared/<str:token>/', views.shared_properties_view, name='shared_properties'),
]
