from django.urls import path
from crm import views

app_name = 'crm'

urlpatterns = [
    # Enquiry form (public)
    path('enquire/<int:property_pk>/', views.enquiry_submit, name='enquiry_submit'),

    # CRM dashboard
    path('', views.LeadsListView.as_view(), name='leads_list'),
    path('leads/<uuid:pk>/', views.LeadDetailView.as_view(), name='lead_detail'),

    # AJAX endpoints
    path('leads/<uuid:pk>/update-status/', views.UpdateLeadStatusView.as_view(), name='update_status'),
    path('leads/<uuid:pk>/reassign/', views.ReassignLeadView.as_view(), name='reassign_lead'),
    path('leads/<uuid:pk>/log-activity/', views.LogActivityView.as_view(), name='log_activity'),
    path('leads/<uuid:pk>/add-followup/', views.AddFollowUpView.as_view(), name='add_followup'),

    # Agent workload & settings (admin only)
    path('agents/', views.AgentWorkloadView.as_view(), name='agent_workload'),
    path('settings/', views.CRMSettingsView.as_view(), name='settings'),

    # Agent self-service
    path('toggle-availability/', views.ToggleAvailabilityView.as_view(), name='toggle_availability'),
]
