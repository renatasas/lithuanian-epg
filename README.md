# Lithuanian Kodi EPG Builder

This repository automatically builds `lt_epg.xml`.

It uses:
- Open-EPG Lithuania as the base XMLTV guide.
- rodo.lt for Lietuvos ryto TV where available.
- the official Lietuvos ryto TV programme page as a fallback/supplement.

The XMLTV channel ID kept for Kodi is:

`Lietuvos ryto televizija.lt`

## Kodi URL

After this repository is uploaded to GitHub and the first workflow run succeeds,
use the **Raw** URL of `lt_epg.xml` as the XMLTV URL in Kodi IPTV Simple Client.

It will look like:

`https://raw.githubusercontent.com/YOUR_GITHUB_NAME/YOUR_REPOSITORY/main/lt_epg.xml`

## Automatic updates

GitHub Actions runs twice per day and can also be started manually from:

Actions -> Build Lithuanian EPG -> Run workflow

## M3U matching

Your M3U entry for Lietuvos ryto TV should contain exactly:

`tvg-id="Lietuvos ryto televizija.lt"`
