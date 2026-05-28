import uuid
from pathlib import Path
from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel
from utils.drf_extensions import OperationLogMixin


def default_remote_metadata_provider_order():
    return {
        "video": ["tmdb", "omdb", "tvdb"],
        "audio": ["musicbrainz", "coverartarchive"],
    }


class Artist(OperationLogMixin, TimeStampedModel):
    """
    Entita' logica artista.

    Non imponiamo subito una tassonomia rigida tra performer/composer/conductor,
    ma il modello e' pronto ad accogliere ruoli multipli tramite ArtistCredit.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    sort_name = models.CharField(max_length=255, blank=True, default="")
    triver_notes = models.TextField(blank=True, default="")
    selected_cover_mode = models.CharField(
        max_length=16,
        choices=[
            ("auto", "auto"),
            ("album", "album"),
            ("upload", "upload"),
        ],
        default="auto",
    )
    selected_cover_album = models.ForeignKey(
        "catalog.Album",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="selected_by_artists",
    )
    selected_profile_image = models.ForeignKey(
        "catalog.ArtistProfileImage",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="selected_by_artists",
    )

    class Meta:
        ordering = ["sort_name", "name"]
        constraints = [
            models.UniqueConstraint(fields=["name", "sort_name"], name="uniq_artist_name_sort_name"),
        ]

    def __str__(self) -> str:
        return self.name


class ArtistProfileImage(OperationLogMixin, TimeStampedModel):
    SOURCE_UPLOAD = "manual_upload"
    SOURCE_CHOICES = [
        (SOURCE_UPLOAD, "manual upload"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    artist = models.ForeignKey(Artist, on_delete=models.CASCADE, related_name="profile_images")
    relative_path = models.CharField(max_length=2048)
    original_filename = models.CharField(max_length=512, blank=True, default="")
    content_type = models.CharField(max_length=128, blank=True, default="")
    size = models.BigIntegerField(default=0)
    source = models.CharField(max_length=32, choices=SOURCE_CHOICES, default=SOURCE_UPLOAD)

    class Meta:
        ordering = ["-created_at", "original_filename"]

    @property
    def absolute_path(self):
        return Path(settings.TRIVER_DUMP_ROOT) / self.relative_path

    def __str__(self) -> str:
        return self.original_filename or self.relative_path


class Album(OperationLogMixin, TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    sort_title = models.CharField(max_length=255, blank=True, default="")
    release_year = models.IntegerField(null=True, blank=True)
    triver_notes = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["sort_title", "title"]

    def __str__(self) -> str:
        return self.title


class Track(OperationLogMixin, TimeStampedModel):
    """
    Entita' logica principale per il playback e le query.

    Un Track puo' essere collegato a uno o piu' file, ma per MVP manteniamo
    un primary_file opzionale e un set di source metadata separati.
    """

    STATE_CLEAN = "clean"
    STATE_MODIFIED = "modified"
    STATE_PENDING_WRITE = "pending_write"
    STATE_SYNCED = "synced"
    STATE_ERROR = "error"
    STATE_CHOICES = [
        (STATE_CLEAN, "clean"),
        (STATE_MODIFIED, "modified"),
        (STATE_PENDING_WRITE, "pending_write"),
        (STATE_SYNCED, "synced"),
        (STATE_ERROR, "error"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    primary_file = models.ForeignKey("library.MediaFile", null=True, blank=True, on_delete=models.SET_NULL, related_name="primary_for_tracks")
    album = models.ForeignKey(Album, null=True, blank=True, on_delete=models.SET_NULL, related_name="tracks")
    canonical_title = models.CharField(max_length=512)
    canonical_sort_title = models.CharField(max_length=512, blank=True, default="")
    release_year = models.IntegerField(null=True, blank=True)
    disc_number = models.IntegerField(null=True, blank=True)
    track_number = models.IntegerField(null=True, blank=True)
    duration_seconds = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    metadata_state = models.CharField(max_length=16, choices=STATE_CHOICES, default=STATE_CLEAN)
    last_error = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["canonical_sort_title", "canonical_title"]

    def __str__(self) -> str:
        return self.canonical_title


class TrackArtistCredit(TimeStampedModel):
    """
    Relazione molti-a-molti con ruolo esplicito.

    Questo e' il punto chiave per supportare query del tipo:
    "dammi tutte le tracce con questa combinazione di artisti, principali o no".
    """

    ROLE_PRIMARY = "primary"
    ROLE_FEATURED = "featured"
    ROLE_COMPOSER = "composer"
    ROLE_CONDUCTOR = "conductor"
    ROLE_PERFORMER = "performer"
    ROLE_CHOICES = [
        (ROLE_PRIMARY, "primary"),
        (ROLE_FEATURED, "featured"),
        (ROLE_COMPOSER, "composer"),
        (ROLE_CONDUCTOR, "conductor"),
        (ROLE_PERFORMER, "performer"),
    ]

    track = models.ForeignKey(Track, on_delete=models.CASCADE, related_name="artist_credits")
    artist = models.ForeignKey(Artist, on_delete=models.CASCADE, related_name="track_credits")
    role = models.CharField(max_length=32, choices=ROLE_CHOICES, default=ROLE_PRIMARY)
    credit_order = models.PositiveIntegerField(default=0)
    credited_name = models.CharField(max_length=255, blank=True, default="")
    is_primary = models.BooleanField(default=False)

    class Meta:
        ordering = ["credit_order", "id"]
        constraints = [
            models.UniqueConstraint(fields=["track", "artist", "role", "credit_order"], name="uniq_track_artist_credit"),
        ]

    def __str__(self) -> str:
        return f"{self.track_id}:{self.artist_id}:{self.role}"


class TrackSourceMetadata(TimeStampedModel):
    """
    Snapshot dei metadata letti da un file specifico.

    Qui teniamo i facts raw, non i valori voluti dall'utente.
    Questo evita di distruggere la distinzione tra sorgente e override.
    """

    track = models.ForeignKey(Track, on_delete=models.CASCADE, related_name="source_metadata")
    media_file = models.ForeignKey("library.MediaFile", on_delete=models.CASCADE, related_name="extracted_metadata")
    extractor_name = models.CharField(max_length=64, default="mutagen")
    extractor_version = models.CharField(max_length=64, blank=True, default="")
    raw_title = models.CharField(max_length=512, blank=True, default="")
    raw_album = models.CharField(max_length=512, blank=True, default="")
    raw_year = models.IntegerField(null=True, blank=True)
    raw_track_number = models.CharField(max_length=64, blank=True, default="")
    raw_disc_number = models.CharField(max_length=64, blank=True, default="")
    raw_artists_display = models.JSONField(default=list, blank=True)
    raw_payload = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]


class TrackMetadataOverride(OperationLogMixin, TimeStampedModel):
    """
    Override espliciti dell'utente.

    Non e' necessario riempire tutto. Si popolano solo i campi che l'utente
    decide di controllare davvero. Il resto continua a derivare dai metadata raw.
    """

    track = models.OneToOneField(Track, on_delete=models.CASCADE, related_name="override")
    title = models.CharField(max_length=512, blank=True, default="")
    album_title = models.CharField(max_length=512, blank=True, default="")
    release_year = models.IntegerField(null=True, blank=True)
    disc_number = models.IntegerField(null=True, blank=True)
    track_number = models.IntegerField(null=True, blank=True)
    comment = models.TextField(blank=True, default="")
    payload = models.JSONField(default=dict, blank=True)

    def __str__(self) -> str:
        return f"override:{self.track_id}"


class TrackVersionGroup(OperationLogMixin, TimeStampedModel):
    """
    Gruppo logico di versioni della stessa opera/traccia.

    Per ora e' una predisposizione: permette di raccogliere piu' Track senza
    decidere ancora se il matching sara' manuale, assistito o automatico.
    """

    SERVING_PRIMARY = "primary"
    SERVING_ALL = "all"
    SERVING_DISABLED = "disabled"
    SERVING_CHOICES = [
        (SERVING_PRIMARY, "primary"),
        (SERVING_ALL, "all"),
        (SERVING_DISABLED, "disabled"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=512)
    sort_title = models.CharField(max_length=512, blank=True, default="")
    fingerprint = models.CharField(max_length=128, blank=True, default="", db_index=True)
    serving_mode = models.CharField(max_length=16, choices=SERVING_CHOICES, default=SERVING_PRIMARY)
    notes = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["sort_title", "title", "created_at"]

    def __str__(self) -> str:
        return self.title


class TrackVersionCandidateDecision(OperationLogMixin, TimeStampedModel):
    STATUS_ACCEPTED = "accepted"
    STATUS_REJECTED = "rejected"
    STATUS_CHOICES = [
        (STATUS_ACCEPTED, "accepted"),
        (STATUS_REJECTED, "rejected"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    fingerprint = models.CharField(max_length=128, unique=True, db_index=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES)
    group = models.ForeignKey(
        TrackVersionGroup,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="candidate_decisions",
    )
    notes = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return f"{self.fingerprint}:{self.status}"


class TrackVersionMembership(OperationLogMixin, TimeStampedModel):
    ROLE_PRIMARY = "primary"
    ROLE_ALTERNATE = "alternate"
    ROLE_LIVE = "live"
    ROLE_REMIX = "remix"
    ROLE_REMASTER = "remaster"
    ROLE_EDIT = "edit"
    ROLE_INSTRUMENTAL = "instrumental"
    ROLE_UNKNOWN = "unknown"
    ROLE_CHOICES = [
        (ROLE_PRIMARY, "primary"),
        (ROLE_ALTERNATE, "alternate"),
        (ROLE_LIVE, "live"),
        (ROLE_REMIX, "remix"),
        (ROLE_REMASTER, "remaster"),
        (ROLE_EDIT, "edit"),
        (ROLE_INSTRUMENTAL, "instrumental"),
        (ROLE_UNKNOWN, "unknown"),
    ]

    group = models.ForeignKey(TrackVersionGroup, on_delete=models.CASCADE, related_name="memberships")
    track = models.ForeignKey(Track, on_delete=models.CASCADE, related_name="version_memberships")
    role = models.CharField(max_length=32, choices=ROLE_CHOICES, default=ROLE_ALTERNATE)
    label = models.CharField(max_length=255, blank=True, default="")
    sort_order = models.PositiveIntegerField(default=0)
    is_default = models.BooleanField(default=False)

    class Meta:
        ordering = ["group", "sort_order", "created_at"]
        constraints = [
            models.UniqueConstraint(fields=["group", "track"], name="uniq_track_version_membership"),
        ]

    def __str__(self) -> str:
        return f"{self.group_id}:{self.track_id}:{self.role}"


class TrackDedupJob(OperationLogMixin, TimeStampedModel):
    STATUS_PENDING = "pending"
    STATUS_RUNNING = "running"
    STATUS_DONE = "done"
    STATUS_ERROR = "error"
    STATUS_CANCELED = "canceled"
    STATUS_CHOICES = [
        (STATUS_PENDING, "pending"),
        (STATUS_RUNNING, "running"),
        (STATUS_DONE, "done"),
        (STATUS_ERROR, "error"),
        (STATUS_CANCELED, "canceled"),
    ]

    MODE_CANDIDATE_SCAN = "candidate_scan"
    MODE_CHOICES = [
        (MODE_CANDIDATE_SCAN, "candidate scan"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    library = models.ForeignKey("library.Library", on_delete=models.CASCADE, related_name="dedup_jobs")
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING)
    mode = models.CharField(max_length=32, choices=MODE_CHOICES, default=MODE_CANDIDATE_SCAN)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    full_throttle_until = models.DateTimeField(null=True, blank=True)
    scanned_count = models.BigIntegerField(default=0)
    candidate_count = models.BigIntegerField(default=0)
    last_error = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"dedup:{self.mode}:{self.status}"


class TrackDedupCandidate(OperationLogMixin, TimeStampedModel):
    STATUS_PENDING = "pending"
    STATUS_ACCEPTED = "accepted"
    STATUS_REJECTED = "rejected"
    STATUS_CHOICES = [
        (STATUS_PENDING, "pending"),
        (STATUS_ACCEPTED, "accepted"),
        (STATUS_REJECTED, "rejected"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    library = models.ForeignKey("library.Library", on_delete=models.CASCADE, related_name="dedup_candidates")
    job = models.ForeignKey(TrackDedupJob, null=True, blank=True, on_delete=models.SET_NULL, related_name="candidates")
    fingerprint = models.CharField(max_length=128, unique=True, db_index=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING)
    title = models.CharField(max_length=512, blank=True, default="")
    score = models.DecimalField(max_digits=4, decimal_places=2, default=0)
    reasons = models.JSONField(default=list, blank=True)
    track_ids = models.JSONField(default=list, blank=True)
    notes = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-score", "title", "-updated_at"]
        indexes = [
            models.Index(fields=["library", "status"], name="dedup_candidate_status_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.title or self.fingerprint}:{self.status}"


class RemoteMetadataSettings(TimeStampedModel):
    LOOKUP_MANUAL = "manual"
    LOOKUP_AUTO = "auto"
    LOOKUP_MODE_CHOICES = [
        (LOOKUP_MANUAL, "manual"),
        (LOOKUP_AUTO, "auto"),
    ]

    OVERWRITE_MISSING_ONLY = "missing_only"
    OVERWRITE_ASK = "ask"
    OVERWRITE_REPLACE_UNLOCKED = "replace_unlocked"
    OVERWRITE_CHOICES = [
        (OVERWRITE_MISSING_ONLY, "missing only"),
        (OVERWRITE_ASK, "ask before overwrite"),
        (OVERWRITE_REPLACE_UNLOCKED, "replace unlocked fields"),
    ]

    enabled = models.BooleanField(default=True)
    lookup_mode = models.CharField(max_length=16, choices=LOOKUP_MODE_CHOICES, default=LOOKUP_MANUAL)
    video_enabled = models.BooleanField(default=True)
    audio_enabled = models.BooleanField(default=True)
    allow_remote_artwork = models.BooleanField(default=True)
    preferred_language = models.CharField(max_length=16, blank=True, default="en-US")
    preferred_region = models.CharField(max_length=8, blank=True, default="US")
    overwrite_policy = models.CharField(max_length=32, choices=OVERWRITE_CHOICES, default=OVERWRITE_MISSING_ONLY)
    provider_order = models.JSONField(default=default_remote_metadata_provider_order, blank=True)

    class Meta:
        verbose_name_plural = "remote metadata settings"

    @classmethod
    def load(cls):
        settings_row, _created = cls.objects.get_or_create(pk=1)
        return settings_row

    def __str__(self) -> str:
        return "remote metadata settings"


class MetadataEnrichmentJob(OperationLogMixin, TimeStampedModel):
    STATUS_PENDING = "pending"
    STATUS_RUNNING = "running"
    STATUS_DONE = "done"
    STATUS_ERROR = "error"
    STATUS_CANCELED = "canceled"
    STATUS_CHOICES = [
        (STATUS_PENDING, "pending"),
        (STATUS_RUNNING, "running"),
        (STATUS_DONE, "done"),
        (STATUS_ERROR, "error"),
        (STATUS_CANCELED, "canceled"),
    ]

    MODE_FIND = "find"
    MODE_REFRESH = "refresh"
    MODE_FIX_MATCH = "fix_match"
    MODE_CHOICES = [
        (MODE_FIND, "find"),
        (MODE_REFRESH, "refresh"),
        (MODE_FIX_MATCH, "fix match"),
    ]

    MEDIA_SCOPE_MIXED = "mixed"
    MEDIA_SCOPE_AUDIO = "audio"
    MEDIA_SCOPE_VIDEO = "video"
    MEDIA_SCOPE_CHOICES = [
        (MEDIA_SCOPE_MIXED, "mixed"),
        (MEDIA_SCOPE_AUDIO, "audio"),
        (MEDIA_SCOPE_VIDEO, "video"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    library = models.ForeignKey("library.Library", null=True, blank=True, on_delete=models.SET_NULL, related_name="metadata_enrichment_jobs")
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="metadata_enrichment_jobs")
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING)
    mode = models.CharField(max_length=32, choices=MODE_CHOICES, default=MODE_FIND)
    media_scope = models.CharField(max_length=16, choices=MEDIA_SCOPE_CHOICES, default=MEDIA_SCOPE_MIXED)
    provider_key = models.CharField(max_length=64, blank=True, default="")
    overwrite_policy = models.CharField(max_length=32, choices=RemoteMetadataSettings.OVERWRITE_CHOICES, default=RemoteMetadataSettings.OVERWRITE_MISSING_ONLY)
    target_track_ids = models.JSONField(default=list, blank=True)
    candidate_count = models.PositiveIntegerField(default=0)
    updated_count = models.PositiveIntegerField(default=0)
    result_payload = models.JSONField(default=dict, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"], name="metadata_enrich_status_idx"),
            models.Index(fields=["media_scope", "created_at"], name="metadata_enrich_scope_idx"),
        ]

    def __str__(self) -> str:
        return f"metadata:{self.mode}:{self.status}"


class MetadataWritebackJob(OperationLogMixin, TimeStampedModel):
    STATUS_PENDING = "pending"
    STATUS_RUNNING = "running"
    STATUS_DONE = "done"
    STATUS_ERROR = "error"
    STATUS_CHOICES = [
        (STATUS_PENDING, "pending"),
        (STATUS_RUNNING, "running"),
        (STATUS_DONE, "done"),
        (STATUS_ERROR, "error"),
    ]

    track = models.ForeignKey(Track, on_delete=models.CASCADE, related_name="writeback_jobs")
    media_file = models.ForeignKey("library.MediaFile", on_delete=models.CASCADE, related_name="writeback_jobs")
    target_format = models.CharField(max_length=32, blank=True, default="native")
    write_native_tags = models.BooleanField(default=True)
    export_triver_sidecar = models.BooleanField(default=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING)
    last_error = models.TextField(blank=True, default="")


class MediaTransformJob(OperationLogMixin, TimeStampedModel):
    """
    Job futuro per conversione o riorganizzazione.

    E' gia' qui per evitare di dover rifare il dominio quando inizierai a spostare
    materiale da ingest/digest verso un layout normalizzato.
    """

    STATUS_PENDING = "pending"
    STATUS_RUNNING = "running"
    STATUS_DONE = "done"
    STATUS_ERROR = "error"
    STATUS_CHOICES = [
        (STATUS_PENDING, "pending"),
        (STATUS_RUNNING, "running"),
        (STATUS_DONE, "done"),
        (STATUS_ERROR, "error"),
    ]

    source_file = models.ForeignKey("library.MediaFile", on_delete=models.CASCADE, related_name="transform_jobs")
    destination_relative_path = models.CharField(max_length=2048)
    destination_format = models.CharField(max_length=32, blank=True, default="")
    requested_profile = models.ForeignKey("library.FileFormatProfile", null=True, blank=True, on_delete=models.SET_NULL)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING)
    last_error = models.TextField(blank=True, default="")
