from types import SimpleNamespace

from django.test import SimpleTestCase

from apps.library.tasks import _infer_video_path_metadata, _split_logical_artists


class VideoPathMetadataInferenceTests(SimpleTestCase):
    def media_file(self, relative_path):
        return SimpleNamespace(relative_path=relative_path, filename=relative_path.rsplit("/", 1)[-1])

    def test_infers_series_from_sxxexx_filename(self):
        metadata = _infer_video_path_metadata(self.media_file("Horace and Pete/Horace.and.Pete.S01E02.Pete.mkv"))

        self.assertEqual(metadata["SeriesTitle"], "Horace and Pete")
        self.assertEqual(metadata["SeasonNumber"], "1")
        self.assertEqual(metadata["EpisodeNumber"], "2")
        self.assertEqual(metadata["EpisodeTitle"], "Pete")

    def test_infers_series_from_season_folder_and_episode_number(self):
        metadata = _infer_video_path_metadata(self.media_file("The Show/Season 02/E03 The Visitor.mp4"))

        self.assertEqual(metadata["SeriesTitle"], "The Show")
        self.assertEqual(metadata["SeasonNumber"], "2")
        self.assertEqual(metadata["EpisodeNumber"], "3")
        self.assertEqual(metadata["EpisodeTitle"], "The Visitor")

    def test_infers_series_from_1x02_pattern(self):
        metadata = _infer_video_path_metadata(self.media_file("Series Name/Series Name - 1x02 - Pilot.mkv"))

        self.assertEqual(metadata["SeriesTitle"], "Series Name")
        self.assertEqual(metadata["SeasonNumber"], "1")
        self.assertEqual(metadata["EpisodeNumber"], "2")
        self.assertEqual(metadata["EpisodeTitle"], "Pilot")

    def test_does_not_infer_series_from_plain_movie_folder(self):
        metadata = _infer_video_path_metadata(self.media_file("1080 Casablanca/1080 Casablanca.mkv"))

        self.assertEqual(metadata, {})

    def test_does_not_infer_series_from_season_folder_without_episode_number(self):
        metadata = _infer_video_path_metadata(self.media_file("The Show/Season 02/The Visitor.mp4"))

        self.assertEqual(metadata, {})


class LogicalArtistSplitTests(SimpleTestCase):
    def test_splits_common_separators_and_keeps_escaped_ampersand(self):
        artists = _split_logical_artists(["Simon \\& Garfunkel, Nina Simone & Miles Davis; Miles Davis"])

        self.assertEqual(artists, ["Simon & Garfunkel", "Nina Simone", "Miles Davis"])
