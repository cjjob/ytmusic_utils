# YTMusic Helper

Simple script to sync local music directory with user library on YTmusic, and manage playlists if you follow a _very constrained naming convention_. All the heavy lifting is done by [this package](https://ytmusicapi.readthedocs.io/en/latest/index.html).

## Authentication

You must manually create the `headers_auth.json` file referenced in the `ytmusic.py` script. This is explained in the link to the package above. The key thing to note is that the HTTP cookie in the headers file will be valid for `min(approx 2 years, while logged in)`.

## Tags

The tagging convention to use is as follows:

- Use square brackets to delimit playlist 'tags', followed by ".mp3".
- Use single lowercase characters to identify playlists.

For example, a local file "my_song [ad].mp3" will be added to playlists "a" and "d" in your Youtube Music library. All the necessary playlist creation/deletion is handled by the script.

## Execution

See [Abseil](https://abseil.io/docs/python/guides/flags) to understand the command line arguments. Most likely, run with:

```console
python3 main.py --sync_library --sync_playlists --noconfirm
```

Note:

- It will create a log file in the working directory.
- Currently, you have to update the library if updating the playlists. i.e. `--nosync_library --sync_playlists` will be bad :(

## TODOs

- Don't delete the files and re-upload when playlist tags change.
- Fix the flushing on command line.
- Handle non-mp3 files.
