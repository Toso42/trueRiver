from django.contrib import admin
from apps.catalog.models import (
    Artist,
    ArtistProfileImage,
    Album,
    Track,
    TrackArtistCredit,
    TrackSourceMetadata,
    TrackMetadataOverride,
    TrackVersionCandidateDecision,
    TrackVersionGroup,
    TrackVersionMembership,
    TrackDedupCandidate,
    TrackDedupJob,
    MetadataWritebackJob,
    MediaTransformJob,
)

admin.site.register(Artist)
admin.site.register(ArtistProfileImage)
admin.site.register(Album)
admin.site.register(Track)
admin.site.register(TrackArtistCredit)
admin.site.register(TrackSourceMetadata)
admin.site.register(TrackMetadataOverride)
admin.site.register(TrackVersionCandidateDecision)
admin.site.register(TrackVersionGroup)
admin.site.register(TrackVersionMembership)
admin.site.register(TrackDedupCandidate)
admin.site.register(TrackDedupJob)
admin.site.register(MetadataWritebackJob)
admin.site.register(MediaTransformJob)
