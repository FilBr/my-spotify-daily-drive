import spotipy
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv
from datetime import datetime, timedelta
import os

load_dotenv()

scope = "playlist-modify-private"
spotify_daily_drive_id = os.environ["SPOTIFY_DAILY_DRIVE_ID"]

sp = spotipy.Spotify(auth_manager=SpotifyOAuth(scope=scope))
dailydrive = sp.playlist(spotify_daily_drive_id)

# Get the tracks from the playlist
tracks = sp.playlist(spotify_daily_drive_id)

# Podcasts IDs
the_essential_podcast_id = os.environ["THE_ESSENTIAL_PODCAST_ID"]
stories_podcast_id = os.environ["STORIES_PODCAST_ID"]
podcasts = [the_essential_podcast_id, stories_podcast_id]


clean_playlist = []
# Clean playlist
for track in tracks["tracks"]["items"][1:]:
    if track["track"]["uri"].startswith("spotify:track:"):
        clean_playlist.append(track["track"])

today = datetime.now().date()
yesterday = today - timedelta(days=1)

podcast_idx = 0
for podcast in podcasts:
    clean_playlist.insert(
        min(len(clean_playlist), podcast_idx), 
        [
            ep
            for ep in sp.show_episodes(the_essential_podcast_id)["items"]
            if datetime.strptime(ep["release_date"], "%Y-%m-%d").date() >= yesterday
        ][0]
    )
    podcast_idx += 3

my_daily_drive_id = os.environ["MY_DAILY_DRIVE_ID"]
sp.playlist_replace_items(my_daily_drive_id, [track["uri"] for track in clean_playlist])
print("Daily Drive updated! 🎶🎧")