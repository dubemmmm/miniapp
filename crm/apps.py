from django.apps import AppConfig


class CrmConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'crm'
    verbose_name = 'CRM'

    def ready(self):
        from django.contrib.auth.signals import user_logged_in

        def _log_login(sender, request, user, **kwargs):
            from crm.activity import log_activity
            from crm.models import ClientActivity
            log_activity(user, ClientActivity.Event.LOGIN)

        user_logged_in.connect(_log_login, dispatch_uid='crm_log_client_login', weak=False)
