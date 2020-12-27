"""Handles """
import getpass
import logging

from absl import app, flags

from ytmusic import YTMusicHelper

logging.basicConfig(
    filename="ytmusic.log",
    filemode="w",  # Overwrite log file
    format="%(asctime)s %(name)s %(module)s %(levelname)s @ Line %(levelno)s : %(message)s",
    level=logging.DEBUG,
)
logger = logging.getLogger(__name__)

FLAGS = flags.FLAGS
# some comment about --upload and or --noupload but probs in the readme

flags.DEFINE_string(
    name="music_dir",
    default=None,
    help="Directory containing music files.",
)
flags.DEFINE_boolean(
    name="upload",
    default=None,
    help="Replace online library with local files.",
)
flags.DEFINE_boolean(
    name="update",
    default=None,
    help="Delete old playlists and recreate using local tags.",
)


def main(argv):
    """Sync library and playlists."""
    if not FLAGS.music_dir:
        user = getpass.getuser()
        FLAGS.music_dir = f"/home/{user}/Music"
        logging.info("Local music directory set to: %s", FLAGS.music_dir)
        # accepted = input('Type "y" if this is correct directory: ')
    ytm_helper = YTMusicHelper(
        FLAGS.music_dir,
        auth_headers="/home/conor/workspace/code/ytmusic/headers_auth.json",
    )

    # Step 1: Upload local first (if at all,
    # otherwise the songs needed for playlist creation might not be there)
    if FLAGS.upload:
        ytm_helper.sync_local_library()

    # Step 2: Do the new playlists
    if FLAGS.update:
        ytm_helper.update_cloud_playlists()


if __name__ == "__main__":
    # flags.mark_flags_as_required(["upload", "update"])
    app.run(main)
