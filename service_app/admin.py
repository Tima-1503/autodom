from django.contrib import admin
from .models import WorkSession, WorkSessionAction, PauseReason

admin.site.register(WorkSession)
admin.site.register(WorkSessionAction)
admin.site.register(PauseReason)