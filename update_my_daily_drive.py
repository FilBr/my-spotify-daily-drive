import os
from datetime import datetime, timedelta

import spotipy
from dotenv import load_dotenv
from spotipy.oauth2 import SpotifyOAuth

load_dotenv()


def main():
    scope = "playlist-modify-private"
    spotify_daily_drive_id = os.environ["SPOTIFY_DAILY_DRIVE_ID"]

    sp = spotipy.Spotify(auth_manager=SpotifyOAuth(scope=scope))
    dailydrive = sp.playlist(spotify_daily_drive_id)

    # Get the tracks from the playlist
    tracks = dailydrive["tracks"]["items"][1:]

    # Podcasts IDs
    the_essential_podcast_id = os.environ["THE_ESSENTIAL_PODCAST_ID"]
    stories_podcast_id = os.environ["STORIES_PODCAST_ID"]

    podcasts = []
    today = datetime.now().date()
    yesterday = today - timedelta(days=1)
    for podcast in [the_essential_podcast_id, stories_podcast_id]:
        latest_episodes = [
            ep
            for ep in sp.show_episodes(podcast)["items"]
            if datetime.strptime(ep["release_date"], "%Y-%m-%d").date() >= yesterday
        ]
        if len(latest_episodes) > 0:
            podcasts.append(latest_episodes[0])

    clean_playlist = []
    # Clean playlist
    for track in tracks:
        if track["track"]["uri"].startswith("spotify:track:"):
            clean_playlist.append(track["track"])

    podcast_idx = 0
    for idx, podcast in enumerate(podcasts):
        clean_playlist.insert(min(len(clean_playlist), podcast_idx), podcast)
        podcast_idx += (idx + 1) + 4

    my_daily_drive_id = os.environ["MY_DAILY_DRIVE_ID"]
    sp.playlist_replace_items(
        my_daily_drive_id, [track["uri"] for track in clean_playlist]
    )
    print(f"[{datetime.now()}] - Daily Drive updated! 🎶🎧")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[{datetime.now()}] - Error: {e}")
        raise e
