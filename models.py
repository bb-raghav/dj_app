from django.db import models
from django.contrib.auth.models import AbstractUser
from datetime import datetime, date


class User(models.Model):
    user_id = models.AutoField(primary_key=True)
    username = models.CharField(max_length=150, unique=True)
    password = models.CharField(max_length=128)  # For bcrypt hashed passwords

    class Meta:
        db_table = "users"
        managed = "False"

    def __str__(self):
        return self.username


class Task(models.Model):
    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, db_column="user_id")
    Title = models.CharField(max_length=200)
    Description = models.TextField(blank=True, null=True)
    due_date = models.DateField()
    is_completed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
  
    class Meta:
        db_table = "tasks"
        ordering = ["-due_date"]
        managed = "False"

    def __str__(self):
        return self.Title

    def serialize(self):
        now = datetime.now().date()

        def ordinal(day):
            if 11 <= day <= 13:
                return f"{day}th"
            else:
                return f"{day}{['th', 'st', 'nd', 'rd', 'th'][min(day % 10, 4)]}"

        base = {
            "id": self.id,
            "Title": self.Title,
            "Description": self.Description or "",
            "due_date": self.due_date.strftime("%Y-%m-%d") if self.due_date else "",
            "is_completed": self.is_completed,
            "due_date_pretty": "",
            "time_left": "",
            "urgency": "none",
        }

        if not self.due_date:
            return base

        try:
            delta = (self.due_date - now).days
            day = self.due_date.day

            urgency_map = {
                "overdue": {"time_left": "Overdue", "urgency": "overdue"},
                "urgent": {"time_left": "Due today", "urgency": "urgent"},
                "warning": {"time_left": f"{delta}d left", "urgency": "warning"},
                "normal": {"time_left": f"{delta}d left", "urgency": "normal"},
            }

            urgency_key = (
                "overdue"
                if delta < 0
                else "urgent"
                if delta == 0
                else "warning"
                if delta <= 2
                else "normal"
            )

            base.update(
                {
                    "due_date_pretty": f"{day}{ordinal(day)[-2:]} {self.due_date.strftime('%b %Y')}",
                    **urgency_map[urgency_key],
                }
            )
        except Exception:
            pass

        return base
