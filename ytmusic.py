import logging
import os
from glob import glob

from ytmusicapi import YTMusic

logger = logging.getLogger(__name__)


class YTMusicHelper:
    def __init__(
        self,
        local_music_dir,
        auth_headers="headers_auth.json",
    ):
        self.music_dir = local_music_dir
        self.ytm_client = YTMusic(auth_headers)
        # TODO: check how to actually validate auth.
        logging.info("Succesfully authenticated.")

    def _get_local_songs(self):
        # Set working directory to location of music files
        os.chdir(self.music_dir)
        # Find matches
        # For `glob`: [[] --> "match a single instance of '['"
        music_files = glob("*[[]*[]].mp3")
        ignored_files = set(glob("*")) - set(music_files)
        logging.info("Ignored the following files:")
        logging.info(ignored_files)
        return music_files

    def _get_cloud_songs(self):
        uploaded_songs = dict()
        uploaded_song_items = self.ytm_client.get_library_upload_songs(
            limit=500000,
            order="a_to_z",
        )

        # We need to keep the song id around in the case where we want to delete it
        for song_item in uploaded_song_items:
            uploaded_songs[song_item["title"]] = song_item["entityId"]

        return uploaded_songs

    def sync_local_library(self):
        # Unidirectional
        # Local --> cloud
        local_song_files = self._get_local_songs()
        cloud_songs = self._get_cloud_songs()

        missing_songs = set(local_song_files) - set(cloud_songs)
        extra_songs = set(cloud_songs) - set(local_song_files)

        import pdb

        pdb.set_trace()
        # Upload new songs
        for song in missing_songs:
            missing_song_filepath = os.path.join(self.music_dir, song)
            self.ytm_client.upload_song(song)

        # Delete "old" songs
        for song in extra_songs():
            song_id = cloud_songs[song]
            self.ytm_client.delete_upload_entity(song_id)

    def _infer_local_playlists(self):
        local_song_files = self._get_local_songs()
        pass

    def _get_playlist_songs(self, playlist_id):
        songs = set()

        playlist_info = self.ytm_client.get_playlist(
            playlistId=playlist_id,
            # If you have more than 10000 songs in a playlist, it's a library mate.
            limit=10000,
        )["tracks"]

        # `song_items` --> list of song info dictionaries
        song_items = playlist_info["tracks"]
        for song_item in song_items:
            song_name = song_item["title"]
            songs.add(song_name)

        return songs

    def get_cloud_playlists(self):
        playlists = {}

        # `playlist_items` --> list of playlist info dictionaries.
        # Keys are: 'title', 'playlistId', 'thumbnails', 'count'.
        playlist_items = self.ytm_client.get_library_playlists()

        for playlist in playlist_items:
            title = playlist["title"]
            playlist_id = playlist["playlistId"]
            # Get titles of all songs in the playlist.
            # FYI: We expect these title to match local files names.
            songs = self._get_playlist_songs(playlist_id)

        return playlists

    def get_history(self):
        pass

    def clear_history(self):
        pass
