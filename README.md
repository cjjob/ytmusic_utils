# YTMusic Scripts

Simple scripts to help manage a user library on YTmusic. All the heavy lifting is done by [this package](https://ytmusicapi.readthedocs.io/en/latest/index.html).

You must manually create the `headers_auth.json` file found in `ytmusic.py` script (you can name the file whatever you like). This is explained in the link to the package above. The key thing to note is that the HTTP cookie in the headers file will be valid for `min(approx 2 years, while logged in).
