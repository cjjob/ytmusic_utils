"""Manage YouTube Music library."""
import getpass
import logging
import os
import time

from absl import app, flags

from ytmusic import YTMusicHelper

logging.basicConfig(
    filename="ytmusic.log",
    filemode="w",  # Overwrite log file
    format="%(asctime)s %(name)s %(module)s %(levelname)s @ Line %(levelno)s : %(message)s",
    level=logging.DEBUG,
)
logger = logging.getLogger(__name__)

# Handles our command line arguments.
# See https://abseil.io/docs/python/guides/flags for more info.
FLAGS = flags.FLAGS
flags.DEFINE_string(
    name="music_dir",
    default=None,
    help="Directory containing music files.",
)
flags.DEFINE_string(
    name="headers",
    default=None,
    help="Full file path to JSON file containing request headers.",
)
flags.DEFINE_boolean(
    name="sync_library",
    default=None,
    help="Replace online library with local files.",
)
flags.DEFINE_boolean(
    name="sync_playlists",
    default=None,
    help="Update online playlists using local tags.",
)
flags.DEFINE_boolean(
    name="confirm",
    default=True,
    help="Require user to confirm default values at terminal before execution.",
)


def main(argv):
    """Sync library and playlists."""
    if not FLAGS.music_dir:
        user = getpass.getuser()
        FLAGS.music_dir = f"/home/{user}/Music"
        logging.info("Local music directory set to: %s", FLAGS.music_dir)
        if FLAGS.confirm:
            accepted = input('Type "y" if this is correct directory: ')
            if accepted.lower() != "y":
                raise Exception("Failed to specify a music directory.")
    if not FLAGS.headers:
        # Assume headers are in same directory as this script.
        path, _ = os.path.split(os.path.realpath(__file__))
        FLAGS.headers = os.path.join(path, "headers_auth.json")
        logging.info("Expecting request headers file at: %s", FLAGS.headers)
        if FLAGS.confirm:
            accepted = input('Type "y" if this is the correct file path: ')
            if accepted.lower() != "y" and FLAGS.confirm:
                raise Exception("Failed to specify a file with request headers.")

    ytm_helper = YTMusicHelper(
        local_music_dir=FLAGS.music_dir,
        headers=FLAGS.headers,
    )

    # Step 1: Library
    if FLAGS.sync_library:
        ytm_helper.sync_local_library()
        # There is a small delay between uploading songs and them being available to
        # manage for playlists. Probably some processing YT does for storage.
        # Hence, small sleep.
        time.sleep(5)

    # Step 2: Playlists
    if FLAGS.sync_playlists:
        ytm_helper.update_cloud_playlists()


if __name__ == "__main__":
    flags.mark_flags_as_required(["sync_library", "sync_playlists"])
    app.run(main)
