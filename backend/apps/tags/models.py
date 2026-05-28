from django.db import models
from django.conf import settings
from django.db.models import Q

from apps.core.models import TimeStampedModel
from utils.drf_extensions import OperationLogMixin


def default_video_curation_row_order():
    return [
        {"type": "system", "key": "recently"},
        {"type": "system", "key": "all"},
    ]


class TagDefinition(OperationLogMixin, TimeStampedModel):
    """
    Definizione di una chiave tag arbitraria.

    La chiave non e' limitata a un vocabolario chiuso del sistema.
    Questo e' intenzionale: Triver deve permettere metadata liberi e query compositive.
    """

    SCOPE_TRACK = "track"
    SCOPE_ALBUM = "album"
    SCOPE_ARTIST = "artist"
    SCOPE_CHOICES = [
        (SCOPE_TRACK, "track"),
        (SCOPE_ALBUM, "album"),
        (SCOPE_ARTIST, "artist"),
    ]

    TYPE_TEXT = "text"
    TYPE_NUMBER = "number"
    TYPE_BOOL = "bool"
    TYPE_DATE = "date"
    TYPE_CHOICES = [
        (TYPE_TEXT, "text"),
        (TYPE_NUMBER, "number"),
        (TYPE_BOOL, "bool"),
        (TYPE_DATE, "date"),
    ]

    VISIBILITY_GLOBAL = "global"
    VISIBILITY_PERSONAL = "personal"
    VISIBILITY_CHOICES = [
        (VISIBILITY_GLOBAL, "global"),
        (VISIBILITY_PERSONAL, "personal"),
    ]

    scope = models.CharField(max_length=16, choices=SCOPE_CHOICES)
    key = models.SlugField(max_length=128)
    label = models.CharField(max_length=255)
    value_type = models.CharField(max_length=16, choices=TYPE_CHOICES, default=TYPE_TEXT)
    allow_multiple = models.BooleanField(default=True)
    description = models.TextField(blank=True, default="")
    visibility = models.CharField(max_length=16, choices=VISIBILITY_CHOICES, default=VISIBILITY_GLOBAL)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE, related_name="tag_definitions")

    class Meta:
        ordering = ["scope", "key"]
        constraints = [
            models.UniqueConstraint(
                fields=["scope", "key"],
                condition=Q(visibility="global"),
                name="uniq_tag_definition_global_scope_key",
            ),
            models.UniqueConstraint(
                fields=["scope", "key", "owner"],
                condition=Q(visibility="personal"),
                name="uniq_tag_definition_personal_scope_key_owner",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.scope}:{self.key}"


class TagValue(TimeStampedModel):
    """
    Valore normalizzato e riusabile di una tag definition.

    Tenere un oggetto TagValue separato rende piu' facile indicizzare e riusare valori,
    invece di spargere JSON ovunque.
    """

    definition = models.ForeignKey(TagDefinition, on_delete=models.CASCADE, related_name="values")
    value_text = models.TextField(blank=True, default="")
    value_number = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    value_bool = models.BooleanField(null=True, blank=True)
    value_date = models.DateField(null=True, blank=True)
    normalized_key = models.CharField(max_length=255, blank=True, default="")
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["definition_id", "display_order", "normalized_key", "id"]

    def __str__(self) -> str:
        if self.definition.value_type == TagDefinition.TYPE_TEXT:
            return self.value_text
        if self.definition.value_type == TagDefinition.TYPE_NUMBER:
            return str(self.value_number)
        if self.definition.value_type == TagDefinition.TYPE_BOOL:
            return str(self.value_bool)
        return str(self.value_date)


class TrackTagAssignment(OperationLogMixin, TimeStampedModel):
    track = models.ForeignKey("catalog.Track", on_delete=models.CASCADE, related_name="tag_assignments")
    tag_value = models.ForeignKey(TagValue, on_delete=models.CASCADE, related_name="track_assignments")

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(fields=["track", "tag_value"], name="uniq_track_tag_assignment"),
        ]

    def __str__(self) -> str:
        return f"{self.track_id}:{self.tag_value_id}"


class AlbumTagAssignment(OperationLogMixin, TimeStampedModel):
    album = models.ForeignKey("catalog.Album", on_delete=models.CASCADE, related_name="tag_assignments")
    tag_value = models.ForeignKey(TagValue, on_delete=models.CASCADE, related_name="album_assignments")

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(fields=["album", "tag_value"], name="uniq_album_tag_assignment"),
        ]

    def __str__(self) -> str:
        return f"{self.album_id}:{self.tag_value_id}"


class ArtistTagAssignment(OperationLogMixin, TimeStampedModel):
    artist = models.ForeignKey("catalog.Artist", on_delete=models.CASCADE, related_name="tag_assignments")
    tag_value = models.ForeignKey(TagValue, on_delete=models.CASCADE, related_name="artist_assignments")

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(fields=["artist", "tag_value"], name="uniq_artist_tag_assignment"),
        ]

    def __str__(self) -> str:
        return f"{self.artist_id}:{self.tag_value_id}"


class VideoCurationSettings(OperationLogMixin, TimeStampedModel):
    row_order = models.JSONField(default=default_video_curation_row_order, blank=True)

    class Meta:
        verbose_name_plural = "video curation settings"

    @classmethod
    def load(cls):
        settings_row, _created = cls.objects.get_or_create(pk=1)
        return settings_row

    def __str__(self) -> str:
        return "video curation settings"
