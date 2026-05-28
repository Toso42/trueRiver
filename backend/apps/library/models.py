import uuid
from pathlib import Path
from django.db import models
from django.db.models import Q

from apps.core.models import TimeStampedModel
from utils.drf_extensions import OperationLogMixin

SUPPORTED_AUDIO_EXTENSIONS = {
    ".mp3",
    ".flac",
    ".wav",
    ".m4a",
    ".ogg",
    ".opus",
    ".aac",
    ".aiff",
    ".wma",
    ".au",
}

SUPPORTED_VIDEO_EXTENSIONS = {
    ".3g2",
    ".3gp",
    ".asf",
    ".avi",
    ".divx",
    ".f4v",
    ".flv",
    ".m2ts",
    ".m4v",
    ".mkv",
    ".mov",
    ".mp4",
    ".mpeg",
    ".mpg",
    ".mts",
    ".mxf",
    ".ogv",
    ".rm",
    ".rmvb",
    ".ts",
    ".vob",
    ".webm",
    ".wmv",
    ".xvid",
}

SUPPORTED_MEDIA_EXTENSIONS = SUPPORTED_AUDIO_EXTENSIONS | SUPPORTED_VIDEO_EXTENSIONS

BROWSER_FRIENDLY_VIDEO_EXTENSIONS = {
    ".mp4",
    ".m4v",
    ".webm",
    ".ogv",
}

LOSSLESS_AUDIO_EXTENSIONS = {
    ".flac",
    ".wav",
    ".aiff",
}

SUPPORTED_ARTWORK_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
}

SUPPORTED_PLAYLIST_EXTENSIONS = {
    ".m3u",
    ".m3u8",
}

SUPPORTED_CUESHEET_EXTENSIONS = {
    ".cue",
}

DIAGNOSTIC_EXTENSIONS = {
    ".log",
    ".db",
}

IGNORED_FILENAMES = {
    ".ds_store",
    "thumbs.db",
    "desktop.ini",
}

DEFAULT_META_FIELD_NAMES = (
    "Album",
    "Artist",
    "TrackName",
    "TrackVersion",
    "SeriesTitle",
    "SeasonNumber",
    "EpisodeNumber",
    "EpisodeTitle",
    "AbsoluteEpisodeNumber",
    "TrackNumber",
    "DiscNumber",
    "ReleaseDate",
    "Genre",
    "Comment",
    "Composer",
    "Conductor",
    "Executor",
    "BandName",
    "EnsembleName",
    "OrchestraName",
    "WorkName",
    "WorkNumber",
    "WorkType",
    "Movement",
    "MovementNumber",
    "ReleaseType",
    "ReleaseLabel",
    "ReleaseCountry",
    "Publisher",
    "Lyrics",
    "SourceMedium",
    "Overview",
    "PosterUrl",
    "BackdropUrl",
    "TMDbId",
    "IMDbId",
    "TVDbId",
    "MusicBrainzRecordingId",
    "MusicBrainzReleaseId",
    "MusicBrainzReleaseGroupId",
    "MusicBrainzArtistId",
)

DEFAULT_META_SEARCH_GROUPS = {
    "artist": (
        "Artist",
        "Executor",
        "Composer",
        "Conductor",
        "BandName",
        "EnsembleName",
        "OrchestraName",
    ),
    "series": (
        "SeriesTitle",
    ),
}

DEFAULT_META_NORMALIZATION_RULES = (
    ("any", "ALBUM", "Album"),
    ("any", "ARTIST", "Artist"),
    ("any", "TRACKNAME", "TrackName"),
    ("any", "TRACKTITLE", "TrackName"),
    ("any", "TITLE", "TrackName"),
    ("any", "TRACKVERSION", "TrackVersion"),
    ("any", "TITLEVERSION", "TrackVersion"),
    ("any", "VERSION", "TrackVersion"),
    ("any", "SUBTITLE", "TrackVersion"),
    ("any", "SERIES", "SeriesTitle"),
    ("any", "SERIE", "SeriesTitle"),
    ("any", "SERIESTITLE", "SeriesTitle"),
    ("any", "SERIESNAME", "SeriesTitle"),
    ("any", "SHOW", "SeriesTitle"),
    ("any", "SHOWTITLE", "SeriesTitle"),
    ("any", "SHOWNAME", "SeriesTitle"),
    ("any", "TVSHOW", "SeriesTitle"),
    ("any", "TVSHOWTITLE", "SeriesTitle"),
    ("any", "SEASON", "SeasonNumber"),
    ("any", "SEASONNO", "SeasonNumber"),
    ("any", "SEASONNUMBER", "SeasonNumber"),
    ("any", "EPISODE", "EpisodeNumber"),
    ("any", "EPISODENO", "EpisodeNumber"),
    ("any", "EPISODENUMBER", "EpisodeNumber"),
    ("any", "EPISODETITLE", "EpisodeTitle"),
    ("any", "EPISODENAME", "EpisodeTitle"),
    ("any", "ABSOLUTEEPISODENUMBER", "AbsoluteEpisodeNumber"),
    ("any", "ABSOLUTEEPISODE", "AbsoluteEpisodeNumber"),
    ("any", "TRACKNUMBER", "TrackNumber"),
    ("any", "TRACK NO", "TrackNumber"),
    ("any", "DISCNUMBER", "DiscNumber"),
    ("any", "DISC NO", "DiscNumber"),
    ("any", "DATE", "ReleaseDate"),
    ("any", "YEAR", "ReleaseDate"),
    ("any", "GENRE", "Genre"),
    ("any", "PERFORMER", "Executor"),
    ("any", "PERFORMERS", "Executor"),
    ("any", "EXECUTOR", "Executor"),
    ("any", "COMMENT", "Comment"),
    ("any", "COMPOSER", "Composer"),
    ("any", "CONDUCTOR", "Conductor"),
    ("any", "BAND", "BandName"),
    ("any", "BANDNAME", "BandName"),
    ("any", "ENSEMBLE", "EnsembleName"),
    ("any", "ENSEMBLENAME", "EnsembleName"),
    ("any", "ORCHESTRA", "OrchestraName"),
    ("any", "ORCHESTRANAME", "OrchestraName"),
    ("any", "WORK", "WorkName"),
    ("any", "WORKNAME", "WorkName"),
    ("any", "WORKNUMBER", "WorkNumber"),
    ("any", "WORK NO", "WorkNumber"),
    ("any", "WORKTYPE", "WorkType"),
    ("any", "MOVEMENT", "Movement"),
    ("any", "MOVEMENTNUMBER", "MovementNumber"),
    ("any", "RELEASETYPE", "ReleaseType"),
    ("any", "RELEASELABEL", "ReleaseLabel"),
    ("any", "LABEL", "ReleaseLabel"),
    ("any", "RELEASECOUNTRY", "ReleaseCountry"),
    ("any", "COUNTRY", "ReleaseCountry"),
    ("any", "PUBLISHER", "Publisher"),
    ("any", "LYRICS", "Lyrics"),
    ("any", "UNSYNCEDLYRICS", "Lyrics"),
    ("any", "SOURCE", "SourceMedium"),
    ("any", "SOURCEMEDIUM", "SourceMedium"),
    ("any", "MEDIUM", "SourceMedium"),
    ("id3", "TALB", "Album"),
    ("id3", "TCOM", "Composer"),
    ("id3", "TCON", "Genre"),
    ("id3", "TDRC", "ReleaseDate"),
    ("id3", "TIT1", "WorkName"),
    ("id3", "TIT2", "TrackName"),
    ("id3", "TIT3", "TrackVersion"),
    ("id3", "TPE1", "Artist"),
    ("id3", "TPE3", "Conductor"),
    ("id3", "TPE4", "Executor"),
    ("id3", "TPUB", "Publisher"),
    ("id3", "TPOS", "DiscNumber"),
    ("id3", "TRCK", "TrackNumber"),
    ("id3", "TYER", "ReleaseDate"),
    ("id3", "COMM", "Comment"),
    ("id3", "USLT", "Lyrics"),
    ("vorbis", "ALBUM", "Album"),
    ("vorbis", "ARTIST", "Artist"),
    ("vorbis", "PERFORMER", "Executor"),
    ("vorbis", "COMMENT", "Comment"),
    ("vorbis", "COMPOSER", "Composer"),
    ("vorbis", "CONDUCTOR", "Conductor"),
    ("vorbis", "ENSEMBLE", "EnsembleName"),
    ("vorbis", "ORCHESTRA", "OrchestraName"),
    ("vorbis", "WORK", "WorkName"),
    ("vorbis", "WORKNAME", "WorkName"),
    ("vorbis", "WORKNUMBER", "WorkNumber"),
    ("vorbis", "MOVEMENT", "Movement"),
    ("vorbis", "MOVEMENTNUMBER", "MovementNumber"),
    ("vorbis", "DATE", "ReleaseDate"),
    ("vorbis", "DISCNUMBER", "DiscNumber"),
    ("vorbis", "GENRE", "Genre"),
    ("vorbis", "TITLE", "TrackName"),
    ("vorbis", "VERSION", "TrackVersion"),
    ("vorbis", "TRACKVERSION", "TrackVersion"),
    ("vorbis", "TRACKNUMBER", "TrackNumber"),
    ("vorbis", "RELEASETYPE", "ReleaseType"),
    ("vorbis", "LABEL", "ReleaseLabel"),
    ("vorbis", "RELEASECOUNTRY", "ReleaseCountry"),
    ("vorbis", "LYRICS", "Lyrics"),
    ("vorbis", "SOURCE", "SourceMedium"),
)


class Library(OperationLogMixin, TimeStampedModel):
    """
    Rappresenta una libreria logica.

    Una libreria punta a tre root fisiche distinte:
    - ingest: materiale ancora grezzo, non ancora digerito dal sistema
    - digest: materiale gia' indicizzato e considerato operativo
    - normalize: output futuri di conversione/riorganizzazione

    Le root stanno anche nei bind mount Docker, ma averle a DB ci permette di gestire
    piu' librerie in futuro senza hardcodare tutto nel deploy.
    """

    name = models.CharField(max_length=128, unique=True)
    slug = models.SlugField(max_length=128, unique=True)
    ingest_path = models.CharField(max_length=1024)
    digest_path = models.CharField(max_length=1024)
    normalize_path = models.CharField(max_length=1024)
    enabled = models.BooleanField(default=True)
    notes = models.TextField(blank=True, default="")
    last_discovery_at = models.DateTimeField(null=True, blank=True)
    last_digest_sync_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class AutoImportSettings(OperationLogMixin, TimeStampedModel):
    library = models.OneToOneField(Library, on_delete=models.CASCADE, related_name="auto_import_settings")
    enabled = models.BooleanField(default=False)
    trive_scan_enabled = models.BooleanField(default=False)
    trive_up_enabled = models.BooleanField(default=False)
    classic_scan_enabled = models.BooleanField(default=False)
    classic_up_enabled = models.BooleanField(default=False)
    last_checked_at = models.DateTimeField(null=True, blank=True)
    last_triggered_at = models.DateTimeField(null=True, blank=True)
    last_trive_signature = models.JSONField(default=dict, blank=True)
    last_classic_signatures = models.JSONField(default=dict, blank=True)
    last_result = models.JSONField(default=dict, blank=True)
    last_error = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["library__name"]

    def __str__(self) -> str:
        return f"auto-import:{self.library.slug}"


class LibraryScanJob(OperationLogMixin, TimeStampedModel):
    """
    Stato di un job di scansione.

    Il job modella la pipeline che hai in mente:
    - discovery single-thread del filesystem
    - processing batch parallelo via Celery
    - contatori atomici e auditabili
    """

    STATUS_PENDING = "pending"
    STATUS_DISCOVERING = "discovering"
    STATUS_PROCESSING = "processing"
    STATUS_DONE = "done"
    STATUS_ERROR = "error"
    STATUS_CANCELED = "canceled"
    STATUS_CHOICES = [
        (STATUS_PENDING, "pending"),
        (STATUS_DISCOVERING, "discovering"),
        (STATUS_PROCESSING, "processing"),
        (STATUS_DONE, "done"),
        (STATUS_ERROR, "error"),
        (STATUS_CANCELED, "canceled"),
    ]

    library = models.ForeignKey(Library, on_delete=models.CASCADE, related_name="scan_jobs")
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING)
    requested_by = models.ForeignKey("auth.User", null=True, blank=True, on_delete=models.SET_NULL)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    discovered_count = models.BigIntegerField(default=0)
    queued_count = models.BigIntegerField(default=0)
    processed_count = models.BigIntegerField(default=0)
    skipped_count = models.BigIntegerField(default=0)
    error_count = models.BigIntegerField(default=0)
    removed_count = models.BigIntegerField(default=0)
    last_error = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"scan:{self.library.slug}:{self.status}"


class LibraryDigestJob(OperationLogMixin, TimeStampedModel):
    """
    Stato di un job di `trive-up`.

    Tiene traccia della costruzione del catalogo logico a partire dai MediaFile gia'
    scoperti in `trive-in`.
    """

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

    library = models.ForeignKey(Library, on_delete=models.CASCADE, related_name="digest_jobs")
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_PENDING)
    requested_by = models.ForeignKey("auth.User", null=True, blank=True, on_delete=models.SET_NULL)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    target_count = models.BigIntegerField(default=0)
    processed_count = models.BigIntegerField(default=0)
    created_track_count = models.BigIntegerField(default=0)
    reused_track_count = models.BigIntegerField(default=0)
    error_count = models.BigIntegerField(default=0)
    last_error = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"digest:{self.library.slug}:{self.status}"


class LibraryDigestError(TimeStampedModel):
    """
    Errore puntuale emerso durante `trive-up`.

    Serve per spiegare all'utente su quale file il digest ha fallito e con quale
    messaggio, senza ridurre tutto a un semplice contatore.
    """

    digest_job = models.ForeignKey(LibraryDigestJob, on_delete=models.CASCADE, related_name="error_records")
    library = models.ForeignKey(Library, on_delete=models.CASCADE, related_name="digest_errors")
    media_file = models.ForeignKey("library.MediaFile", null=True, blank=True, on_delete=models.SET_NULL, related_name="digest_errors")
    relative_path = models.CharField(max_length=2048, blank=True, default="")
    absolute_path = models.CharField(max_length=4096)
    filename = models.CharField(max_length=512)
    message = models.TextField(blank=True, default="")
    error_type = models.CharField(max_length=128, blank=True, default="")

    class Meta:
        ordering = ["relative_path", "filename", "created_at"]
        indexes = [
            models.Index(fields=["digest_job"], name="digest_error_job_idx"),
        ]

    @property
    def display_path(self) -> str:
        if self.relative_path:
            path = Path(self.relative_path)
            if path.parent == Path("."):
                return path.name
            return f"{path.parent}/{path.name}"
        return self.filename

    def __str__(self) -> str:
        return self.display_path


class SavedPlaylist(OperationLogMixin, TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    library = models.ForeignKey(Library, on_delete=models.CASCADE, related_name="saved_playlists")
    name = models.CharField(max_length=255)
    notes = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["name", "-updated_at"]
        constraints = [
            models.UniqueConstraint(fields=["library", "name"], name="uniq_saved_playlist_library_name"),
        ]

    def __str__(self) -> str:
        return self.name


class SavedPlaylistEntry(TimeStampedModel):
    playlist = models.ForeignKey(SavedPlaylist, on_delete=models.CASCADE, related_name="entries")
    track = models.ForeignKey("catalog.Track", on_delete=models.CASCADE, related_name="saved_playlist_entries")
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["position", "id"]
        constraints = [
            models.UniqueConstraint(fields=["playlist", "position"], name="uniq_saved_playlist_entry_position"),
        ]

    def __str__(self) -> str:
        return f"{self.playlist_id}:{self.position}"


class SourceFolder(TimeStampedModel):
    """
    Cartella sorgente emersa da `trive-in`.

    Questo modello conserva il contesto umano della raccolta originale:
    - nome cartella
    - profondita'
    - relazione padre/figlio
    - numero di file media e accessori che contiene

    Serve come base per `trive-up`, dove i metadati embedded da soli non bastano.
    """

    library = models.ForeignKey(Library, on_delete=models.CASCADE, related_name="source_folders")
    relative_path = models.CharField(max_length=2048, blank=True, default="")
    absolute_path = models.CharField(max_length=4096)
    name = models.CharField(max_length=512)
    parent_relative_path = models.CharField(max_length=2048, blank=True, default="")
    path_depth = models.PositiveIntegerField(default=0)
    file_count = models.PositiveIntegerField(default=0)
    audio_file_count = models.PositiveIntegerField(default=0)
    accessory_file_count = models.PositiveIntegerField(default=0)
    first_seen_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)
    removed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["relative_path", "name"]
        constraints = [
            models.UniqueConstraint(fields=["library", "relative_path"], name="uniq_source_folder_per_library_path"),
        ]
        indexes = [
            models.Index(fields=["library", "path_depth"], name="sourcefolder_library_depth_idx"),
        ]

    @property
    def display_path(self) -> str:
        return self.relative_path or self.name

    def get_best_cover_accessory(self):
        folder_aliases = {self.relative_path}
        unrevisioned_prefix = "Unrevisioned/"
        if self.relative_path.startswith(unrevisioned_prefix):
            folder_aliases.add(self.relative_path[len(unrevisioned_prefix):])
        elif self.relative_path:
            folder_aliases.add(f"{unrevisioned_prefix}{self.relative_path}")

        folder_filter = Q(source_folder=self)
        for folder_alias in folder_aliases:
            if not folder_alias:
                continue
            folder_filter |= Q(source_folder__relative_path=folder_alias)
            folder_filter |= Q(relative_path__startswith=f"{folder_alias}/")

        artwork_files = AccessoryFile.objects.filter(
            library=self.library,
            asset_kind=AccessoryFile.KIND_ARTWORK,
        ).filter(folder_filter).distinct().order_by("-size", "-mtime", "filename")
        active_cover = artwork_files.filter(removed_at__isnull=True).first()
        if active_cover:
            return active_cover

        for cover in artwork_files:
            candidates = []
            if cover.absolute_path:
                candidates.append(Path(cover.absolute_path))
            if cover.relative_path:
                relative_path = Path(cover.relative_path)
                candidates.extend([
                    Path(cover.library.ingest_path) / relative_path,
                    Path(cover.library.digest_path) / relative_path,
                    Path(cover.library.digest_path) / "Unrevisioned" / relative_path,
                ])
            if any(candidate.exists() and candidate.is_file() for candidate in candidates):
                return cover
        return None

    def __str__(self) -> str:
        return self.display_path


class MediaFile(OperationLogMixin, TimeStampedModel):
    """
    File fisico osservato sul filesystem.

    Questo modello resta volutamente vicino al file reale.
    Non va confuso con Track/Album/Artist, che sono entita' logiche.
    """

    STATUS_DISCOVERED = "discovered"
    STATUS_INDEXED = "indexed"
    STATUS_MODIFIED = "modified"
    STATUS_PENDING_WRITE = "pending_write"
    STATUS_SYNCED = "synced"
    STATUS_ERROR = "error"
    STATUS_MISSING = "missing"
    STATUS_CHOICES = [
        (STATUS_DISCOVERED, "discovered"),
        (STATUS_INDEXED, "indexed"),
        (STATUS_MODIFIED, "modified"),
        (STATUS_PENDING_WRITE, "pending_write"),
        (STATUS_SYNCED, "synced"),
        (STATUS_ERROR, "error"),
        (STATUS_MISSING, "missing"),
    ]

    STORAGE_STAGE_TRIV_IN = "triv_in"
    STORAGE_STAGE_TRIV_UP = "triv_up"
    STORAGE_STAGE_EXTERNAL = "external"
    STORAGE_STAGE_CHOICES = [
        (STORAGE_STAGE_TRIV_IN, "triv_in"),
        (STORAGE_STAGE_TRIV_UP, "triv_up"),
        (STORAGE_STAGE_EXTERNAL, "external"),
    ]

    WORKFLOW_UNPROCESSED = "unprocessed"
    WORKFLOW_UNREVISIONED = "unrevisioned"
    WORKFLOW_REVISED = "revised"
    WORKFLOW_EXACT_DUPLICATE = "exact_duplicate"
    WORKFLOW_VARIANT = "variant"
    WORKFLOW_CHOICES = [
        (WORKFLOW_UNPROCESSED, "unprocessed"),
        (WORKFLOW_UNREVISIONED, "unrevisioned"),
        (WORKFLOW_REVISED, "revised"),
        (WORKFLOW_EXACT_DUPLICATE, "exact_duplicate"),
        (WORKFLOW_VARIANT, "variant"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    library = models.ForeignKey(Library, on_delete=models.CASCADE, related_name="media_files")
    source_folder = models.ForeignKey(
        SourceFolder,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="media_files",
    )
    relative_path = models.CharField(max_length=2048)
    absolute_path = models.CharField(max_length=4096)
    path_hash = models.CharField(max_length=64, db_index=True)
    filename = models.CharField(max_length=512)
    extension = models.CharField(max_length=32, blank=True, default="")
    media_kind = models.CharField(max_length=32, blank=True, default="audio")
    mime_type = models.CharField(max_length=128, blank=True, default="")
    size = models.BigIntegerField(default=0)
    mtime = models.DateTimeField(null=True, blank=True)
    inode = models.CharField(max_length=64, blank=True, default="")
    content_hash = models.CharField(max_length=128, blank=True, default="")
    storage_stage = models.CharField(max_length=16, choices=STORAGE_STAGE_CHOICES, default=STORAGE_STAGE_TRIV_IN)
    workflow_state = models.CharField(max_length=24, choices=WORKFLOW_CHOICES, default=WORKFLOW_UNPROCESSED)
    digest_relative_path = models.CharField(max_length=2048, blank=True, default="")
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_DISCOVERED)
    first_seen_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)
    removed_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["relative_path"]
        constraints = [
            models.UniqueConstraint(fields=["library", "relative_path"], name="uniq_media_file_per_library_path"),
        ]
        indexes = [
            models.Index(fields=["library", "path_hash"], name="mediafile_library_hash_idx"),
            models.Index(fields=["library", "status"], name="mediafile_library_status_idx"),
            models.Index(fields=["mtime", "size"], name="mediafile_mtime_size_idx"),
        ]

    @property
    def display_path(self) -> str:
        path = Path(self.relative_path)
        if path.parent == Path("."):
            return path.name
        return f"{path.parent}/{path.name}"

    def __str__(self) -> str:
        return self.relative_path


class MetaFieldDefinition(OperationLogMixin, TimeStampedModel):
    """
    Definizione dinamica di un campo metadata incontrato nei file.

    Il vocabolario non e' chiuso: Triver crea nuovi field quando incontra chiavi nuove
    o quando l'utente decide di indicizzarle esplicitamente.
    """

    name = models.CharField(max_length=255, unique=True)
    normalized_name = models.CharField(max_length=255, unique=True, db_index=True)
    source_family = models.CharField(max_length=32, blank=True, default="any")
    is_user_defined = models.BooleanField(default=False)
    is_indexed = models.BooleanField(default=True)
    description = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["normalized_name", "name"]

    def __str__(self) -> str:
        return self.name


class MetaNormalizationRule(TimeStampedModel):
    """
    Mappa un nome metadata incontrato in un formato verso un campo interno Triver.
    """

    source_family = models.CharField(max_length=32, default="any")
    source_name = models.CharField(max_length=255)
    source_name_normalized = models.CharField(max_length=255, db_index=True)
    target_field = models.ForeignKey(
        MetaFieldDefinition,
        on_delete=models.CASCADE,
        related_name="normalization_rules",
    )
    is_active = models.BooleanField(default=True)
    is_system = models.BooleanField(default=False)

    class Meta:
        ordering = ["source_family", "source_name_normalized"]
        constraints = [
            models.UniqueConstraint(
                fields=["source_family", "source_name_normalized"],
                name="uniq_meta_normalization_rule_source",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.source_family}:{self.source_name} -> {self.target_field.name}"


class MediaFileMetaValue(TimeStampedModel):
    """
    Valore metadata letto da un file e associato a un MetaFieldDefinition.

    Un MediaFile puo' avere piu' valori per lo stesso campo: ad esempio artist multipli.
    """

    media_file = models.ForeignKey(
        MediaFile,
        on_delete=models.CASCADE,
        related_name="meta_values",
    )
    field = models.ForeignKey(
        MetaFieldDefinition,
        on_delete=models.CASCADE,
        related_name="values",
    )
    source_family = models.CharField(max_length=32, default="unknown")
    source_name = models.CharField(max_length=255)
    source_name_normalized = models.CharField(max_length=255, db_index=True)
    value_text = models.TextField(blank=True, default="")
    value_order = models.PositiveIntegerField(default=0)
    is_primary = models.BooleanField(default=False)

    class Meta:
        ordering = ["field__normalized_name", "value_order", "id"]
        indexes = [
            models.Index(fields=["media_file", "field"], name="media_meta_file_field_idx"),
            models.Index(fields=["field", "source_family"], name="media_meta_field_family_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.media_file_id}:{self.field.name}={self.value_text}"


class AccessoryFile(TimeStampedModel):
    """
    File accessorio osservato nella cartella di input.

    Non e' una traccia, ma puo' essere molto utile in fase di revisione:
    - artwork
    - cue sheet
    - playlist
    - file diagnostici
    - support file non ancora classificati
    """

    KIND_ARTWORK = "artwork"
    KIND_PLAYLIST = "playlist"
    KIND_CUE_SHEET = "cue_sheet"
    KIND_DIAGNOSTIC = "diagnostic"
    KIND_UNKNOWN_SUPPORT = "unknown_support"
    KIND_CHOICES = [
        (KIND_ARTWORK, "artwork"),
        (KIND_PLAYLIST, "playlist"),
        (KIND_CUE_SHEET, "cue_sheet"),
        (KIND_DIAGNOSTIC, "diagnostic"),
        (KIND_UNKNOWN_SUPPORT, "unknown_support"),
    ]

    library = models.ForeignKey(Library, on_delete=models.CASCADE, related_name="accessory_files")
    source_folder = models.ForeignKey(
        SourceFolder,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="accessory_files",
    )
    relative_path = models.CharField(max_length=2048)
    absolute_path = models.CharField(max_length=4096)
    filename = models.CharField(max_length=512)
    extension = models.CharField(max_length=32, blank=True, default="")
    asset_kind = models.CharField(max_length=64, choices=KIND_CHOICES)
    size = models.BigIntegerField(default=0)
    mtime = models.DateTimeField(null=True, blank=True)
    first_seen_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)
    removed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["relative_path", "filename"]
        constraints = [
            models.UniqueConstraint(fields=["library", "relative_path"], name="uniq_accessory_file_per_library_path"),
        ]
        indexes = [
            models.Index(fields=["library", "asset_kind"], name="accessory_library_kind_idx"),
        ]

    @property
    def display_path(self) -> str:
        path = Path(self.relative_path)
        if path.parent == Path("."):
            return path.name
        return f"{path.parent}/{path.name}"

    def __str__(self) -> str:
        return self.display_path


class LibraryScanSkip(TimeStampedModel):
    """
    Record esplicito di un file visto durante la scansione ma non accettato.

    MediaFile resta riservato ai file che Triver considera ingestibili come media validi.
    Questo modello conserva invece gli scarti con il motivo, cosi' la UI puo'
    spiegare all'utente cosa e' successo.
    """

    REASON_UNSUPPORTED_EXTENSION = "unsupported_extension"
    REASON_ARTWORK_ASSET = "artwork_asset"
    REASON_PLAYLIST_ASSET = "playlist_asset"
    REASON_CUE_SHEET = "cue_sheet"
    REASON_DIAGNOSTIC_FILE = "diagnostic_file"
    REASON_IGNORED_SYSTEM_FILE = "ignored_system_file"
    REASON_UNKNOWN_EXTENSION = "unknown_extension"
    REASON_STAT_FAILED = "stat_failed"
    REASON_NOT_A_FILE = "not_a_file"
    REASON_PERMISSION_DENIED = "permission_denied"
    REASON_UNKNOWN_ERROR = "unknown_error"
    REASON_CHOICES = [
        (REASON_UNSUPPORTED_EXTENSION, "unsupported_extension"),
        (REASON_ARTWORK_ASSET, "artwork_asset"),
        (REASON_PLAYLIST_ASSET, "playlist_asset"),
        (REASON_CUE_SHEET, "cue_sheet"),
        (REASON_DIAGNOSTIC_FILE, "diagnostic_file"),
        (REASON_IGNORED_SYSTEM_FILE, "ignored_system_file"),
        (REASON_UNKNOWN_EXTENSION, "unknown_extension"),
        (REASON_STAT_FAILED, "stat_failed"),
        (REASON_NOT_A_FILE, "not_a_file"),
        (REASON_PERMISSION_DENIED, "permission_denied"),
        (REASON_UNKNOWN_ERROR, "unknown_error"),
    ]

    scan_job = models.ForeignKey(LibraryScanJob, on_delete=models.CASCADE, related_name="skip_records")
    library = models.ForeignKey(Library, on_delete=models.CASCADE, related_name="scan_skips")
    relative_path = models.CharField(max_length=2048, blank=True, default="")
    absolute_path = models.CharField(max_length=4096)
    filename = models.CharField(max_length=512)
    extension = models.CharField(max_length=32, blank=True, default="")
    size = models.BigIntegerField(null=True, blank=True)
    reason_code = models.CharField(max_length=64, choices=REASON_CHOICES)
    reason_detail = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["relative_path", "filename", "created_at"]
        indexes = [
            models.Index(fields=["scan_job", "reason_code"], name="scan_skip_job_reason_idx"),
        ]

    @property
    def display_path(self) -> str:
        if self.relative_path:
            path = Path(self.relative_path)
            if path.parent == Path("."):
                return path.name
            return f"{path.parent}/{path.name}"
        return self.filename

    def __str__(self) -> str:
        return self.display_path


class FileFormatProfile(TimeStampedModel):
    """
    Descrive un profilo di formato che Triver considera rilevante.

    Serve per future conversioni e normalizzazione.
    Non e' solo un elenco di estensioni: permette di definire policy interne.
    """

    name = models.CharField(max_length=64, unique=True)
    container = models.CharField(max_length=32)
    codec = models.CharField(max_length=64, blank=True, default="")
    is_lossless = models.BooleanField(default=False)
    writeback_supported = models.BooleanField(default=False)
    notes = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name
