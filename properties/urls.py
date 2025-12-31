from django.urls import path
from . import views

urlpatterns = [
    path('default', views.landing_view, name='landing'),
    path('home', views.home, name='home'),
    path('register/', views.register_view, name='register'),
    path('employee-register/', views.employee_register_view, name='employee_register'),
    path('api/properties/', views.properties_api, name='properties_api'),
    path('api/properties/<int:property_id>/', views.property_detail_api, name='property_detail_api'),
    path('api/properties/<int:property_id>/favorite/', views.toggle_favorite, name='toggle_favorite'),
    path('favorites/', views.favorites_view, name='favorites'),
    path('api/create-shared-list/', views.create_shared_list, name='create_shared_list'),
    path('property/<int:property_id>/pdf/', views.download_property_pdf, name='property_pdf'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('manage-shares/', views.manage_shared_lists, name='manage_shared_lists'),
    path('manage-shares/delete/<int:list_id>/', views.delete_shared_list, name='delete_shared_list'),
    path('manage-shares/toggle/<int:list_id>/', views.toggle_shared_list, name='toggle_shared_list'),
    path('api/property/<int:property_id>/request-unlock/', views.request_property_unlock, name='request_property_unlock'),
    path('api/compare-properties/', views.compare_properties, name='compare_properties'),
    path('api/comparison-properties/<str:property_ids>/', views.comparison_pdf, name='comparison_pdf'),
    path('api/validate-invitation/', views.validate_invitation_code, name='validate_invitation'),
    path('google-oauth-signup/', views.google_oauth_with_invitation, name='google_oauth_signup'),
    path('shared/<str:token>/', views.shared_properties_view, name='shared_properties'),
    path('', views.temp_view, name='temp')
]
