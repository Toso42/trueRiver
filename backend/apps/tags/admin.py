from django.contrib import admin
from apps.tags.models import TagDefinition, TagValue, TrackTagAssignment

admin.site.register(TagDefinition)
admin.site.register(TagValue)
admin.site.register(TrackTagAssignment)
