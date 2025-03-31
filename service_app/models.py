from django.db import models

# Create your models here.
from django.db import models
import json

class WorkSession(models.Model):
    session_id = models.CharField(max_length=36, unique=True)
    worker_code = models.CharField(max_length=50)
    order_number = models.CharField(max_length=50)
    work_code = models.CharField(max_length=50)
    executor = models.CharField(max_length=100)
    intervals = models.TextField(default='[]')  # JSON-строка
    current_start = models.CharField(max_length=50, null=True, blank=True)
    time_left = models.IntegerField(null=True, blank=True)
    initial_time_left = models.IntegerField(default=0)

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    work_description = models.TextField(default='', blank=True)
    last_action = models.CharField(max_length=20, null=True, blank=True)
    pause_reason_code = models.CharField(max_length=10, null=True, blank=True)
    def set_intervals(self, intervals_list):
        self.intervals = json.dumps(intervals_list, ensure_ascii=False)

    def get_intervals(self):
        return json.loads(self.intervals)