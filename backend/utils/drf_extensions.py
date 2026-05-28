import datetime
from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.db import models
from rest_framework import serializers, viewsets


class OperationLogMixin(models.Model):
    """Versione alleggerita del mixin usato in `ar`, adattata a Triver."""

    class Meta:
        abstract = True

    def log_operation(self, user, operation, changes=None, path=None, http_method=None):
        OperationLog = apps.get_model("core", "OperationLog")

        def normalize(value):
            if isinstance(value, dict):
                return {k: normalize(v) for k, v in value.items()}
            if isinstance(value, list):
                return [normalize(v) for v in value]
            if isinstance(value, (datetime.date, datetime.datetime)):
                return value.isoformat()
            if isinstance(value, models.Model):
                return str(value.pk)
            return value

        OperationLog.objects.create(
            user=user,
            operation=operation,
            content_type=ContentType.objects.get_for_model(self.__class__),
            object_id=str(self.pk),
            changes=normalize(changes) if changes else None,
            path=path or "",
            http_method=http_method or "",
        )

    def save(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        path = kwargs.pop("path", None)
        http_method = kwargs.pop("http_method", None)
        is_new = self.pk is None
        changes = None

        if not is_new:
            try:
                old = self.__class__.objects.get(pk=self.pk)
                changes = {}
                for field in self._meta.fields:
                    old_value = getattr(old, field.name)
                    new_value = getattr(self, field.name)
                    if old_value != new_value:
                        changes[field.name] = [old_value, new_value]
            except self.__class__.DoesNotExist:
                changes = None

        super().save(*args, **kwargs)

        if user is not None:
            self.log_operation(user, "create" if is_new else "update", changes=changes, path=path, http_method=http_method)

    def delete(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        path = kwargs.pop("path", None)
        http_method = kwargs.pop("http_method", None)
        snapshot = {field.name: getattr(self, field.name) for field in self._meta.fields}
        if user is not None:
            self.log_operation(user, "delete", changes=snapshot, path=path, http_method=http_method)
        return super().delete(*args, **kwargs)


class LoggedModelSerializer(serializers.ModelSerializer):
    def save(self, **kwargs):
        self._log_user = kwargs.pop("user", None)
        self._log_path = kwargs.pop("path", None)
        self._log_method = kwargs.pop("http_method", None)
        return super().save(**kwargs)

    def create(self, validated_data):
        instance = self.Meta.model(**validated_data)
        if isinstance(instance, OperationLogMixin):
            instance.save(user=self._log_user, path=self._log_path, http_method=self._log_method)
        else:
            instance.save()
        return instance

    def update(self, instance, validated_data):
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if isinstance(instance, OperationLogMixin):
            instance.save(user=self._log_user, path=self._log_path, http_method=self._log_method)
        else:
            instance.save()
        return instance


class LoggedViewSetMixin(viewsets.ModelViewSet):
    def perform_create(self, serializer):
        user = self.request.user if getattr(self.request.user, "is_authenticated", False) else None
        serializer.save(user=user, path=self.request.path, http_method=self.request.method)

    def perform_update(self, serializer):
        user = self.request.user if getattr(self.request.user, "is_authenticated", False) else None
        serializer.save(user=user, path=self.request.path, http_method=self.request.method)

    def perform_destroy(self, instance):
        user = self.request.user if getattr(self.request.user, "is_authenticated", False) else None
        if isinstance(instance, OperationLogMixin):
            instance.delete(user=user, path=self.request.path, http_method=self.request.method)
        else:
            instance.delete()


class BidirectionalRelationMixin:
    """
    Placeholder compatibile col nome usato in `ar`.

    Per ora Triver mantiene relazioni esplicite e serializer chiari.
    Il mixin resta disponibile per futura logica di sync bidirezionale.
    """

    pass
