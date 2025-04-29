from django.db import models
import json
from django.db import models
class WorkSession(models.Model):
    session_id = models.CharField(max_length=36, unique=True)
    worker_code = models.CharField(max_length=50)
    order_number = models.CharField(max_length=50)
    work_code = models.CharField(max_length=50)
    executor = models.CharField(max_length=100)
    intervals = models.TextField(default='[]')
    current_start = models.CharField(max_length=20, null=True, blank=True)
    time_left = models.IntegerField(default=0)
    initial_time_left = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    work_description = models.TextField(null=True, blank=True)
    is_finished = models.BooleanField(default=False)
    def set_intervals(self, intervals_list):
        self.intervals = json.dumps(intervals_list, ensure_ascii=False)

    def get_intervals(self):
        return json.loads(self.intervals)

    def __str__(self):
        return f"{self.worker_code} - {self.work_code} ({'Active' if self.is_active else 'Inactive'})"



class WorkSessionAction(models.Model):
    session = models.ForeignKey(WorkSession, on_delete=models.CASCADE, related_name='actions')
    action = models.CharField(max_length=20)  # "start", "pause", "resume", "finish"
    reason_code = models.CharField(max_length=10, null=True, blank=True)  # Для паузы
    start = models.CharField(max_length=20, null=True, blank=True)  # Время начала
    end = models.CharField(max_length=20, null=True, blank=True)  # Время окончания
    timestamp = models.DateTimeField(auto_now_add=True)  # Время действия

    def __str__(self):
        return f"{self.session.work_code} - {self.action} at {self.timestamp}"

# Новая модель PauseReason
class PauseReason(models.Model):
    code = models.CharField(max_length=10, unique=True, verbose_name="Код причины")
    description = models.CharField(max_length=100, verbose_name="Описание причины")

    def __str__(self):
        return f"{self.code} - {self.description}"

    class Meta:
        verbose_name = "Причина паузы"
        verbose_name_plural = "Причины паузы"

