from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils.timezone import now


class TimeStampedModel(models.Model):
    """Base leggibile e riusabile per quasi tutte le entita' operative."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class OperationLog(models.Model):
    """
    Audit log minimale.

    Per Triver e' utile soprattutto per tracciare:
    - editing di metadata
    - assegnazione tag
    - operazioni di scan e write-back avviate da utenti o servizi
    """

    OPERATION_CHOICES = [
        ("create", "create"),
        ("read", "read"),
        ("update", "update"),
        ("delete", "delete"),
        ("action", "action"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    operation = models.CharField(max_length=16, choices=OPERATION_CHOICES)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.CharField(max_length=64)
    target = GenericForeignKey("content_type", "object_id")
    timestamp = models.DateTimeField(default=now)
    path = models.CharField(max_length=255, blank=True, default="")
    http_method = models.CharField(max_length=16, blank=True, default="")
    changes = models.JSONField(null=True, blank=True)

    class Meta:
        ordering = ["-timestamp", "-id"]

    def __str__(self) -> str:
        return f"[{self.timestamp}] {self.operation} {self.content_type}:{self.object_id}"
