"""Helper module for managing library uploads and playlists.

The module assumes a specific naming/tagging convention of local files in order for the
playlist management to function automatically."""

import collections
import logging
import os
import re
import sys
from glob import glob

from ytmusicapi import YTMusic

logger = logging.getLogger(__name__)


class YTMusicHelper:
    """Wrapper around API to help with some simple tasks."""

    def __init__(
        self,
        local_music_dir,
        auth_headers="headers_auth.json",
    ):
        self.music_dir = local_music_dir
        self.ytm_client = YTMusic(auth_headers)

    def _get_local_songs(self):
        """Searches the specified `local_music_dir` for .mp3 files with the naming
        convention described previously, i.e. square brackets capturing playlist tags.

        Returns:
            list(str): Files are returned as "song_name [playlist_info].mp3", not the
                full path.
        """
        # Set working directory to location of music files.
        os.chdir(self.music_dir)

        # Find matches.
        # For `glob`, the expression "[[]" means "match a single instance of '['"
        music_files = glob("*[[]*[]].mp3")

        # We also report any non matches. That is, any other file in the folder.
        ignored_files = set(glob("*")) - set(music_files)
        logging.info("Ignored the following files:")
        logging.info(ignored_files)

        return music_files

    def _get_cloud_songs(self):
        """Get information about songs that already have been uploaded to the library.

        We will get a dictionary:
            song_name: entity_id

        We want these for two reasons:
        1) We can avoid re-uploading everything which would be much slower.
        2) We need to delete the song in the case where it has changed locally. This
        might happen because we (1) changed the playlists it belongs to, (2) we do are
        fixing a typo, (3) we simply do not want it anymore, etc.

        Returns:
            dict: The entity ids of the songs (i.e. their titles) in the uploaded
                library.
        """
        # Get all songs and info (per song).
        uploaded_songs = dict()
        uploaded_song_items = self.ytm_client.get_library_upload_songs(
            limit=500000,
            order="a_to_z",
        )

        # Retain the song title and id.
        for song_item in uploaded_song_items:
            uploaded_songs[song_item["title"]] = song_item["videoId"]

        return uploaded_songs

    def sync_local_library(self):
        """This is a unidirectional sync: local --> cloud.

        After running this the YouTube library will contain exactly (therefore ONLY) the
        the files that exist in the local music directory.

        We apply changes based on deltas, i.e.
        (1) Upload any missing songs.
        (2) Delete any previously uploaded songs that do not match locally.

        N.B. if you change the actual file locally but keep the name the same (e.g.
        better quality, different version, etc.) the file will not change.
        TODO: Check file hash instead.
        """
        # Get libraries in both locations.
        local_song_files = self._get_local_songs()
        cloud_songs = self._get_cloud_songs()

        # Work out deltas.
        missing_songs = set(local_song_files) - set(cloud_songs)
        extra_songs = set(cloud_songs) - set(local_song_files)

        # Upload new songs.
        missing_songs_total = len(missing_songs)
        uploaded = 0
        for song in missing_songs:
            missing_song_filepath = os.path.join(self.music_dir, song)
            self.ytm_client.upload_song(missing_song_filepath)

            # Progress output.
            uploaded += 1
            # TODO: Handle flushing for variable line length.
            sys.stdout.write(f"\rUploading {song} [{uploaded}/{missing_songs_total}]")
            sys.stdout.flush()

        # Delete "old" songs.
        extra_songs_total = len(extra_songs)
        deleted = 0
        for song in extra_songs:
            song_id = cloud_songs[song]
            self.ytm_client.delete_upload_entity(song_id)

            # Progress output.
            deleted += 1
            sys.stdout.write(f"\rDeleting {song} [{deleted}/{extra_songs_total}]")
            sys.stdout.flush()

    def _parse_song_playlist(self, filename):
        """Given a song filename, work out the playlists it belongs to based on the
        tagging convention. e.g.
        "song_name [as].mp3" would need to be added to playlists titled "a" and "s".

        Args:
            filename (str): The name of the file as "song_name [playlist_info].mp3", not
            the full path.

        Returns:
            list(str): The playlist titles the song should be added to.
        """
        # Construct regex to validate the string.
        # Note this is more involved than the earlier `glob` check.
        # TODO: Explain the regex.
        # TODO: Do this proper check earlier.
        regex = r"^[^\[\]]+(\[[A-Za-z]*\])\.mp3$"
        regex = re.compile(regex)
        regex_error = f'Song "{filename}" does not follow expected naming convention.'
        assert regex.match(filename), regex_error

        # Get the string between the brackets and convert to list
        playlist_tags = list(filename[filename.find("[") + 1 : filename.find("]")])

        return playlist_tags

    def _infer_local_playlists(self):
        """Get all the playlists for the local library.

        Returns:
            list: The playlists each song should be added to.
        """
        local_song_filepaths = self._get_local_songs()

        playlists = collections.defaultdict(list)

        for song_filepath in local_song_filepaths:
            _, song_filename = os.path.split(song_filepath)
            playlist_tags = self._parse_song_playlist(song_filename)
            for tag in playlist_tags:
                # Note, we're going to save the FULL FILEPATH for the output
                playlists[tag].append(song_filepath)

        return playlists

    def _get_playlist_songs(self, playlist_id):
        songs = set()

        playlist_info = self.ytm_client.get_playlist(
            playlistId=playlist_id,
            # If you have more than 10000 songs in a playlist, it's a library mate.
            limit=10000,
        )

        # `song_items` --> list of song info dictionaries
        song_items = playlist_info["tracks"]
        for song_item in song_items:
            song_name = song_item["title"]
            songs.add(song_name)

        return songs

    def _delete_old_playlists(self):
        # `playlist_items` --> list of playlist info dictionaries.
        # Keys are: 'title', 'playlistId', 'thumbnails', 'count'.
        playlist_items = self.ytm_client.get_library_playlists()

        for playlist in playlist_items:
            playlist_name = playlist["title"]
            # We only want the kind of playlists we want
            # Note all the playlists
            # Note, we could do something
            if playlist_name.isalpha() and len(playlist_name) == 1:
                playlist_id = playlist["playlistId"]
                print(f"Deleting playlist {playlist_name} with id {playlist_id}")
                self.ytm_client.delete_playlist(playlist_id)

    def update_cloud_playlists(self):
        # Strategy is to delete old playlists
        # and recreate from scratch using local tag info

        # Step 1: Delete
        self._delete_old_playlists()

        # Step 2: Create
        local_playlists = self._infer_local_playlists()
        # TODO: Probably a nicer way to do this than potentially query for this twice.
        uploaded_songs = self._get_cloud_songs()

        # For each playlist we need to get the corresponding entity ids.
        # Once we have them we create the new playlists with the appropriate title.
        playlists_to_update = len(local_playlists)
        updated = 0
        for local_playlist in local_playlists:
            song_names = local_playlists[local_playlist]
            song_ids = []
            for song in song_names:
                # Get entity id from library information.
                song_id = uploaded_songs[song]
                song_ids.append(song_id)
            #
            self.ytm_client.create_playlist(
                title=local_playlist,
                description="",
                video_ids=song_ids,
            )
            # Progress output.
            updated += 1
            sys.stdout.write(
                f"\rUpdating playlist {local_playlist} [{updated}/{playlists_to_update}]",
            )
            sys.stdout.flush()
