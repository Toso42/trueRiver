from django.contrib import admin
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.api.views import (
    AccessoryFileViewSet,
    AlbumTagAssignmentViewSet,
    AlbumViewSet,
    ArtistTagAssignmentViewSet,
    ArtistViewSet,
    AutoImportSettingsViewSet,
    AuthViewSet,
    csrf_token_view,
    LibraryDigestErrorViewSet,
    LibraryDigestJobViewSet,
    LibraryViewSet,
    LibraryScanJobViewSet,
    LibraryScanSkipViewSet,
    MediaFileViewSet,
    MetadataEnrichmentJobViewSet,
    MediaFileMetaValueViewSet,
    MetaFieldDefinitionViewSet,
    MetaNormalizationRuleViewSet,
    QuickSearchViewSet,
    RemoteMetadataSettingsViewSet,
    SavedPlaylistViewSet,
    IngestBrowserViewSet,
    SourceFolderViewSet,
    SystemMaintenanceViewSet,
    TrackDedupCandidateViewSet,
    TrackDedupJobViewSet,
    TrackViewSet,
    TrackVersionGroupViewSet,
    TrackVersionMembershipViewSet,
    VideoCurationSettingsViewSet,
    VideoViewSet,
    TagDefinitionViewSet,
    TagValueViewSet,
    TrackTagAssignmentViewSet,
)

router = DefaultRouter()
router.register("libraries", LibraryViewSet, basename="library")
router.register("auto-import", AutoImportSettingsViewSet, basename="auto-import")
router.register("auth", AuthViewSet, basename="auth")
router.register("scan-jobs", LibraryScanJobViewSet, basename="scan-job")
router.register("digest-jobs", LibraryDigestJobViewSet, basename="digest-job")
router.register("digest-errors", LibraryDigestErrorViewSet, basename="digest-error")
router.register("scan-skips", LibraryScanSkipViewSet, basename="scan-skip")
router.register("source-folders", SourceFolderViewSet, basename="source-folder")
router.register("ingest-browser", IngestBrowserViewSet, basename="ingest-browser")
router.register("accessory-files", AccessoryFileViewSet, basename="accessory-file")
router.register("media-files", MediaFileViewSet, basename="media-file")
router.register("remote-metadata-settings", RemoteMetadataSettingsViewSet, basename="remote-metadata-setting")
router.register("metadata-enrichment-jobs", MetadataEnrichmentJobViewSet, basename="metadata-enrichment-job")
router.register("meta-fields", MetaFieldDefinitionViewSet, basename="meta-field")
router.register("meta-normalization-rules", MetaNormalizationRuleViewSet, basename="meta-normalization-rule")
router.register("quick-search", QuickSearchViewSet, basename="quick-search")
router.register("media-file-meta-values", MediaFileMetaValueViewSet, basename="media-file-meta-value")
router.register("albums", AlbumViewSet, basename="album")
router.register("artists", ArtistViewSet, basename="artist")
router.register("tracks", TrackViewSet, basename="track")
router.register("videos", VideoViewSet, basename="video")
router.register("video-curation", VideoCurationSettingsViewSet, basename="video-curation")
router.register("saved-playlists", SavedPlaylistViewSet, basename="saved-playlist")
router.register("tag-definitions", TagDefinitionViewSet, basename="tag-definition")
router.register("tag-values", TagValueViewSet, basename="tag-value")
router.register("track-tags", TrackTagAssignmentViewSet, basename="track-tag")
router.register("album-tags", AlbumTagAssignmentViewSet, basename="album-tag")
router.register("artist-tags", ArtistTagAssignmentViewSet, basename="artist-tag")
router.register("track-dedup-jobs", TrackDedupJobViewSet, basename="track-dedup-job")
router.register("track-dedup-candidates", TrackDedupCandidateViewSet, basename="track-dedup-candidate")
router.register("track-version-groups", TrackVersionGroupViewSet, basename="track-version-group")
router.register("track-version-memberships", TrackVersionMembershipViewSet, basename="track-version-membership")
router.register("system", SystemMaintenanceViewSet, basename="system")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/getcsrf/", csrf_token_view, name="csrf-token"),
    path("api/", include(router.urls)),
]
