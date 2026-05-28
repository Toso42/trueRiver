from django.contrib import admin
from apps.library.models import AutoImportSettings, Library, LibraryScanJob, MediaFile, FileFormatProfile

admin.site.register(AutoImportSettings)
admin.site.register(Library)
admin.site.register(LibraryScanJob)
admin.site.register(MediaFile)
admin.site.register(FileFormatProfile)
