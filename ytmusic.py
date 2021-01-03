"""Helper module for managing library uploads and playlists.

The module assumes a specific naming/tagging convention of local files in order for the
playlist management to function properly.

In brief, have lowercase alphabet characters in square brackets [] immediately preceding
the .mp3 file extension. See README.md for more details.
"""

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
        headers,
    ):
        self.music_dir = local_music_dir
        self.ytm_client = YTMusic(headers)

    def _get_local_songs(self):
        """Searches the specified `local_music_dir` for .mp3 files with the naming
        convention described previously, i.e. square brackets capturing playlist tags.

        We only want to bother with this step once. Hence, the try/except AttributeError
        structure. That directory won't change during execution so this is a safe (i.e.
        we do not need to worry that our information is out of date.)

        Returns:
            list(str): Files are returned as "song_name [playlist_info].mp3", not the
                full path.
        """
        try:
            return self.local_songs
        except AttributeError:
            # Set working directory to location of music files.
            os.chdir(self.music_dir)

            # Find matches.
            # For `glob`, the expression "[[]" means "match a single instance of '['"
            self.local_songs = glob("*[[]*[]].mp3")

            # We also report any non matches. That is, any other file in the folder.
            ignored_files = set(glob("*")) - set(self.local_songs)
            logging.info("Ignored the following files:")
            logging.info(ignored_files)

            return self.local_songs

    def _get_cloud_songs(self, force_update=False):
        """Get information about songs that already have been uploaded to the library.
        We use the try/except block to avoid repeatedly running this operation if we
        have already queried once.

        The IDs we get from this query will help for a few reasons:
        1) We can avoid re-uploading everything which would be much slower.
        2) We need to delete the song in the case where it has changed locally. This
        might happen because we (1) changed the playlists it belongs to, (2) we do are
        fixing a typo, (3) we simply do not want it anymore, etc.
        3) We need the ID information when editing playlists.

        Returns:
            dict: Song titles (in uploaded library) mapped to IDs.
        """

        def get_songs():
            uploaded_songs = dict()
            uploaded_song_items = self.ytm_client.get_library_upload_songs(
                limit=500000,
                order="a_to_z",
            )

            # Retain the song title and various IDs.
            for song_item in uploaded_song_items:
                uploaded_songs[song_item["title"]] = {
                    "entityId": song_item["entityId"],  # Needed for deletion.
                    "videoId": song_item["videoId"],  # Needed for playlist management.
                }

            return uploaded_songs

        try:
            if force_update:
                self.uploaded_songs = get_songs()
            return self.uploaded_songs
        except AttributeError:
            self.uploaded_songs = get_songs()
            return self.uploaded_songs

    def sync_local_library(self):
        """This is a unidirectional sync: local --> cloud.

        After running this the YouTube library will contain exactly (therefore ONLY) the
        the files that exist in the local music directory.

        We apply changes based on deltas, i.e.
        (1) Upload any missing songs.
        (2) Delete any previously uploaded songs that do not match locally.

        N.B. if you change the actual file locally but keep the name the same (e.g.
        better quality, different version, etc.) the file will not change. TODO: Check
        file hash instead to avoid this problem.
        """
        # Get libraries in both locations.
        local_song_files = self._get_local_songs()
        cloud_songs = self._get_cloud_songs()

        # Work out deltas.
        missing_songs = set(local_song_files) - set(cloud_songs)
        extra_songs = set(cloud_songs) - set(local_song_files)

        # Delete "old" songs.
        extra_songs_total = len(extra_songs)
        for i, song in enumerate(extra_songs, 1):
            song_id = cloud_songs[song]["entityId"]
            sys.stdout.write(f"\rDeleting {song} [{i}/{extra_songs_total}]")
            delete_result = self.ytm_client.delete_upload_entity(song_id)
            assert (
                delete_result == "STATUS_SUCCEEDED"
            ), f"Failed to delete {song}. Response from request: {delete_result}."
            sys.stdout.flush()

        # Upload new songs.
        missing_songs_total = len(missing_songs)
        for i, song in enumerate(missing_songs, 1):
            missing_song_filepath = os.path.join(self.music_dir, song)
            sys.stdout.write(f"\rUploading {song} [{i}/{missing_songs_total}]")
            upload_result = self.ytm_client.upload_song(missing_song_filepath)
            assert (
                upload_result == "STATUS_SUCCEEDED"
            ), f"Failed to upload {song}. Response from request: {upload_result}"
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
            dict: Playlist titles as keys and where each value is a list of songs to be
            added. The songs in the list are the full local file PATH.
        """
        local_song_filepaths = self._get_local_songs()

        playlists = collections.defaultdict(list)

        for song_filepath in local_song_filepaths:
            _, song_filename = os.path.split(song_filepath)
            # Work which playlists, if any, this song needs to belong to.
            playlist_tags = self._parse_song_playlist(song_filename)
            for tag in playlist_tags:
                playlists[tag].append(song_filepath)

        return playlists

    def _match_playlists(self, local_playlists):
        """Updates cloud playlists to be the same set as local playlists. To be clear,
        we are updating the playlists themselves, NOT the songs in the playlists.

        Steps:
        1: Get the playlists that exist in cloud library.
        2: Remove/add playlists to match local.
        2.1: Work out what playlists we have already (and therefore, do not need to
        create).
        2.2: Take care that we are reliant on a naming convention. We only edit
        playlists with a single character. Otherwise, a playlist like "my random songs"
        would be deleted.

        Args:
            local_playlists (list): Each element is the name/title of a playlist that we
            want.

        Returns:
            dict: {"title": "playlist_id"}
        """
        cloud_playlists = dict()

        # Step 1
        playlist_items = self.ytm_client.get_library_playlists()

        # Step 2
        for playlist in playlist_items:
            playlist_name = playlist["title"]
            playlist_id = playlist["playlistId"]
            # Step 2.1
            if playlist_name in local_playlists:
                # Remove so we do not attemp to create later.
                local_playlists.remove(playlist_name)
                cloud_playlists[playlist_name] = playlist_id
            # Step 2.2
            elif len(playlist_name) > 1:
                pass
            else:
                logging.info(
                    "Deleting playlist %s with id %s",
                    playlist_name,
                    playlist_id,
                )
                deletion_result = self.ytm_client.delete_playlist(playlist_id)
                # This seems to be the best way to validate success for now.
                # The dictionary just has different keys. And nothing nested in the
                # dictionary seems to indicate success obviously.
                # TODO: Find a better check?
                assert "error" not in deletion_result, "Failed to delete playlist."

        # Anything still in `local_playlists` must not exist so we need to create.
        for missing_local_playlist in local_playlists:
            creation_result = self.ytm_client.create_playlist(
                title=missing_local_playlist,
                description="",
            )
            # Looks like success is just the playlist ID, but failure is a dictionary.
            # This check will do for now.
            # TODO: Find a better check?
            assert isinstance(
                creation_result, str
            ), "Playlist wasn't created - maybe...(?)"
            cloud_playlists[missing_local_playlist] = creation_result

        return cloud_playlists

    def _get_cloud_playlist_songs(self, playlist_id):
        """Get all the songs (titles) in a given cloud playlists.

        Args:
            playlist_id (str): The entity ID of the playlist.

        Returns:
            dict: Contains YouTube library IDs required to manage playlist items.
        """
        songs = dict()

        playlist_info = self.ytm_client.get_playlist(
            playlistId=playlist_id,
            # If you have more than 10000 songs in a playlist, it's a library mate.
            limit=10000,
        )
        song_items = playlist_info["tracks"]
        for song_item in song_items:
            songs[song_item["title"]] = {
                "videoId": song_item["videoId"],
                "setVideoId": song_item["setVideoId"],
            }

        return songs

    def _match_playlist_items(self, playlist_id, songs):
        """Updates an existing cloud playlist to have all and only the songs provided
        with the argument.

        The function assumes all songs passed are available in the user's cloud library.

        Steps:
        1: Remove unnecessary songs.
        2: Add new songs.

        Args:
            playlist_id (str): The entity ID of the playlists to be updated.
            songs (list[str]): The song names. This should match the "title" key from
            the YouTube API response.
        """
        # It would probably be easier to just straight up remove all the items and add
        # from scratch but whatever...
        # This will be a dictionary of dictionaries:
        # {"song_name": {"videoId": ..., "setVideoId": ...,}, ...}
        cloud_playlist = self._get_cloud_playlist_songs(playlist_id)

        # Step 1
        songs_to_remove = {  # Songs in the cloud playlist but not required.
            song: ids for song, ids in cloud_playlist.items() if song not in songs
        }
        if len(songs_to_remove) > 0:
            # Here we need both the videoId and setVideoId
            # They just have to be keys in a dictionary for each item (where the item)
            # is a list.
            result = self.ytm_client.remove_playlist_items(
                playlistId=playlist_id,
                videos=[*songs_to_remove.values()],
            )

            assert (
                result == "STATUS_SUCCEEDED"
            ), f"Failed to remove items to playlist with ID: {playlist_id}"

        # Step 2
        songs_to_add = {  # Songs required but not in the cloud playlist.
            song: id for song, id in songs.items() if song not in cloud_playlist
        }
        if len(songs_to_add) >= 1:
            # In this case we just need the video id
            result = self.ytm_client.add_playlist_items(
                playlistId=playlist_id,
                videoIds=[*songs_to_add.values()],
            )
            assert (
                result == "STATUS_SUCCEEDED"
            ), f"Failed to add items to playlist with ID: {playlist_id}"

    def update_cloud_playlists(self):
        """The easiest option to code is to delete all playlists and then recreate from
        scratch (because the operation(s) are so cheap).
        However, you can easily hit the YouTube API limit for playlist creation if this
        method is used.
        Instead we will do the "proper" version. That is, we will edit the playlists and
        only create and delete when genuinely required.

        Steps:
        1: Work out what playlists should exist using local information, i.e. tags at
        the end of file names.
        2: Create/delete cloud playlists to match local.
        3: Update playlists. That is, add/remove the items in the playlists.
        """
        # Step 1
        local_playlists = self._infer_local_playlists()  # Dict of {playlist: songs}
        required_playlists = [*local_playlists]  # Get the keys (i.e. playlist names)

        # Step 2
        cloud_playlists = self._match_playlists(required_playlists)

        # Step 3
        uploaded_songs = self._get_cloud_songs(force_update=True)

        # For each playlist we need to get the corresponding entity (playlist) IDs.
        # Once we have them we create the new playlists with the appropriate title.
        playlists_to_update = len(local_playlists)
        updated = 0

        for local_playlist in local_playlists:
            song_names = local_playlists[local_playlist]
            songs = dict()
            # For each song in each playlist we need to get the YouTube Music ID to be
            # able to manage it.
            for song in song_names:
                song_id = uploaded_songs[song]["videoId"]
                songs[song] = song_id
            # Get target cloud playlist ID
            playlist_id = cloud_playlists[local_playlist]

            # Progress output.
            updated += 1
            sys.stdout.write(
                f"\rUpdating playlist {local_playlist} [{updated}/{playlists_to_update}]",
            )
            sys.stdout.flush()
            self._match_playlist_items(playlist_id, songs)
