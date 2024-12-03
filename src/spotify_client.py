import json
import logging
import os
from http.cookiejar import MozillaCookieJar
from typing import Dict, List, Optional
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup

from base import (
    AccountAttributes,
    Album,
    Artist,
    Category,
    ExternalUrl,
    Image,
    MusicProviderClient,
    Owner,
    Playlist,
    PlaylistTrack,
    Profile,
    Track,
)

logger = logging.getLogger(__name__)


class SpotifyClient(MusicProviderClient):
    """
    Spotify implementation of the MusicProviderClient.
    """

    def __init__(self, cookie_file: Optional[str] = None):
        self.base_url = "https://api-partner.spotify.com"
        self.session_data = None
        self.config_data = None
        self.client_token = None
        self.cookies = None
        if cookie_file:
            self._load_cookies(cookie_file)

    def _load_cookies(self, cookie_file: str) -> None:
        """
        Load cookies from a file.

        :param cookie_file: Path to the cookie file.
        """
        if not os.path.exists(cookie_file):
            logger.error(f"Cookie file not found: {cookie_file}")
            raise FileNotFoundError(f"Cookie file not found: {cookie_file}")

        cookie_jar = MozillaCookieJar(cookie_file)
        cookie_jar.load(ignore_discard=True, ignore_expires=True)
        self.cookies = requests.utils.dict_from_cookiejar(cookie_jar)

    def authenticate(self, credentials: Optional[dict] = None) -> None:
        """
        Authenticate with Spotify using cookies if available, or fetch session and config data.

        :param credentials: Optional dictionary of credentials.
        """
        if self.cookies:
            logger.debug("Authenticating using cookies.")
            self.session_data, self.config_data = self._fetch_session_data()
            self.client_token = self._fetch_client_token()
        else:
            logger.debug("Authenticating without cookies.")
            self.session_data, self.config_data = self._fetch_session_data(
                fetch_with_cookies=False
            )
            self.client_token = self._fetch_client_token()

    def _fetch_session_data(self, fetch_with_cookies: bool = True):
        """
        Fetch session data from Spotify.

        :param fetch_with_cookies: Whether to include cookies in the request.
        :return: Tuple containing session and config data.
        """
        url = "https://open.spotify.com/"
        headers = {
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        }
        cookies = self.cookies if fetch_with_cookies else None
        response = requests.get(url, headers=headers, cookies=cookies)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        session_script = soup.find("script", {"id": "session"})
        config_script = soup.find("script", {"id": "config"})
        if session_script and config_script:
            logger.debug("fetched session and config scripts")
            return json.loads(session_script.string), json.loads(config_script.string)
        else:
            raise ValueError("Failed to fetch session or config data.")

    def _fetch_client_token(self):
        """
        Fetch the client token using session data and cookies.

        :return: The client token as a string.
        """
        url = "https://clienttoken.spotify.com/v1/clienttoken"
        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "origin": "https://open.spotify.com",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        }
        payload = {
            "client_data": {
                "client_version": "1.2.52.404.gcb99a997",
                "client_id": self.session_data.get("clientId", ""),
                "js_sdk_data": {
                    "device_brand": "unknown",
                    "device_model": "unknown",
                    "os": "windows",
                    "os_version": "NT 10.0",
                    "device_id": self.config_data.get("correlationId", ""),
                    "device_type": "computer",
                },
            }
        }
        response = requests.post(
            url, headers=headers, json=payload, cookies=self.cookies
        )
        response.raise_for_status()
        logger.debug("fetched granted_token")
        return response.json().get("granted_token", "")

    def _make_request(self, endpoint: str, params: dict = None) -> dict:
        """
        Helper method to make authenticated requests to Spotify APIs.
        """
        headers = {
            "accept": "application/json",
            "app-platform": "WebPlayer",
            "authorization": f'Bearer {self.session_data.get("accessToken", "")}',
            "client-token": self.client_token.get("token", ""),
        }
        logger.debug(f"starting request: {self.base_url}/{endpoint}")
        response = requests.get(
            f"{self.base_url}/{endpoint}",
            headers=headers,
            params=params,
            cookies=self.cookies,
        )

        response.raise_for_status()
        return response.json()

    # region utility functions to help parsing objects
    def _parse_external_urls(self, uri: str, entity_type: str) -> List[ExternalUrl]:
        """
        Create ExternalUrl instances for an entity.

        :param uri: The URI of the entity.
        :param entity_type: The type of entity ('track', 'album', 'artist', 'playlist', etc.).
        :return: A list of ExternalUrl instances.
        """
        return [
            ExternalUrl(
                url=f"https://open.spotify.com/{entity_type}/{uri.split(':')[-1]}"
            )
        ]

    def _parse_images(self, image_data: List[Dict]) -> List[Image]:
        """
        Parse images from the API response.

        :param image_data: List of dictionaries containing image data.
        :return: A list of Image objects.
        """
        images = []
        for img in image_data:
            # Extract the first source if available
            sources = img.get("sources", [])
            if sources:
                source = sources[0]  # Take the first source as the default
                images.append(
                    Image(
                        url=source.get("url"),
                        height=source.get("height"),
                        width=source.get("width"),
                    )
                )
        return images

    def _parse_artist(self, artist_data: Dict) -> Artist:
        """
        Parse an artist object from API data.

        :param artist_data: Dictionary representing an artist.
        :return: An Artist instance.
        """
        return Artist(
            id=artist_data["uri"].split(":")[-1],
            name=artist_data["profile"]["name"],
            uri=artist_data["uri"],
            external_urls=self._parse_external_urls(artist_data["uri"], "artist"),
        )

    def _parse_album(self, album_data: Dict) -> Album:
        """
        Parse an album object from API data.

        :param album_data: Dictionary representing an album.
        :return: An Album instance.
        """
        return Album(
            id=album_data["uri"].split(":")[-1],
            name=album_data["name"],
            uri=album_data["uri"],
            external_urls=self._parse_external_urls(album_data["uri"], "album"),
            artists=[
                self._parse_artist(artist) for artist in album_data["artists"]["items"]
            ],
            images=self._parse_images(album_data["coverArt"]["sources"]),
        )

    def _parse_track(self, track_data: Dict) -> Track:
        """
        Parse a track object from API data.

        :param track_data: Dictionary representing a track.
        :return: A Track instance.
        """
        return Track(
            id=track_data["uri"].split(":")[-1],
            name=track_data["name"],
            uri=track_data["uri"],
            external_urls=self._parse_external_urls(track_data["uri"], "track"),
            duration_ms=(
                track_data["trackDuration"]["totalMilliseconds"]
                if "trackDuration" in track_data
                else track_data["episodeDuration"]["totalMilliseconds"]
            ),
            explicit=track_data.get("explicit", False),
            album=(
                self._parse_album(track_data["albumOfTrack"])
                if "albumOfTrack" in track_data
                else None
            ),
            artists=(
                [
                    self._parse_artist(artist)
                    for artist in track_data["artists"]["items"]
                ]
                if "artists" in track_data
                else []
            ),
        )

    def _parse_owner(self, owner_data: Dict) -> Optional[Owner]:
        """
        Parse an owner object from API data.

        :param owner_data: Dictionary representing an owner.
        :return: An Owner instance or None if the owner data is empty.
        """
        if not owner_data:
            return None

        return Owner(
            id=owner_data.get("uri", "").split(":")[-1],
            name=owner_data.get("name", ""),
            uri=owner_data.get("uri", ""),
            external_urls=self._parse_external_urls(owner_data.get("uri", ""), "user"),
        )

    # endregion

    def get_playlist(self, playlist_id: str) -> Playlist:
        """
        Fetch a playlist by ID with all tracks, using the defined generic classes.
        """
        limit = 50
        offset = 0
        all_items = []

        while True:
            query_parameters = {
                "operationName": "fetchPlaylist",
                "variables": json.dumps(
                    {
                        "uri": "spotify:playlist:{playlist_id}".format(
                            playlist_id=playlist_id
                        ),
                        "offset": offset,
                        "limit": limit,
                    }
                ),
                "extensions": json.dumps(
                    {
                        "persistedQuery": {
                            "version": 1,
                            "sha256Hash": "19ff1327c29e99c208c86d7a9d8f1929cfdf3d3202a0ff4253c821f1901aa94d",
                        }
                    }
                ),
            }
            encoded_query = urlencode(query_parameters)
            data = self._make_request(f"pathfinder/v1/query?{encoded_query}")
            playlist_data = data.get("data", {}).get("playlistV2", {})
            content = playlist_data.get("content", {})
            items = content.get("items", [])
            all_items.extend(items)

            if len(all_items) >= content.get("totalCount", 0):
                break

            offset += limit

        # Use utility methods to parse tracks
        tracks = [self._parse_track(item["itemV2"]["data"]) for item in all_items]

        images = self._parse_images(playlist_data.get("images", {}).get("items", []))

        owner_data = playlist_data.get("ownerV2", {}).get("data", {})
        owner = self._parse_owner(owner_data)

        return Playlist(
            id=playlist_id,
            name=playlist_data.get("name", ""),
            uri=playlist_data.get("uri", ""),
            external_urls=self._parse_external_urls(playlist_id, "playlist"),
            description=playlist_data.get("description", ""),
            public=playlist_data.get("public", None),
            collaborative=playlist_data.get("collaborative", None),
            followers=playlist_data.get("followers", 0),
            images=images,
            owner=owner,
            tracks=[
                PlaylistTrack(
                    added_at=item.get("addedAt", {}).get("isoString", ""),
                    added_by=None,
                    is_local=False,
                    track=track,
                )
                for item, track in zip(all_items, tracks)
            ],
        )

    def search_tracks(self, query: str, limit: int = 10) -> List[Track]:
        """
        Searches for tracks on Spotify.
        :param query: Search query.
        :param limit: Maximum number of results.
        :return: A list of Track objects.
        """
        print(
            f"search_tracks: Placeholder for search with query '{query}' and limit {limit}."
        )
        return []

    def get_track(self, track_id: str) -> Track:
        """
        Fetches details for a specific track.
        :param track_id: The ID of the track.
        :return: A Track object.
        """
        print(f"get_track: Placeholder for track with ID {track_id}.")
        return Track(
            id=track_id,
            name="",
            uri="",
            duration_ms=0,
            explicit=False,
            album=Album(),
            artists=[],
            external_urls=ExternalUrl(),
        )

    def get_featured_playlists(self, limit: int = 10) -> List[Playlist]:
        """
        Fetches featured playlists.
        :param limit: Maximum number of results.
        :return: A list of Playlist objects.
        """
        print(
            f"get_featured_playlists: Placeholder for featured playlists with limit {limit}."
        )
        return []

    def get_playlists_by_category(
        self, category_id: str, limit: int = 10
    ) -> List[Playlist]:
        """
        Fetches playlists for a specific category.
        :param category_id: The ID of the category.
        :param limit: Maximum number of results.
        :return: A list of Playlist objects.
        """
        print(
            f"get_playlists_by_category: Placeholder for playlists in category {category_id}."
        )
        return []

    def get_categories(self, limit: int = 10) -> List[Category]:
        """
        Fetches categories from Spotify.
        :param limit: Maximum number of results.
        :return: A list of Category objects.
        """
        print(f"get_categories: Placeholder for categories with limit {limit}.")
        return []

    # non generic method implementations:
    def get_profile(self) -> Optional[Profile]:
        """
        Fetch the profile attributes of the authenticated Spotify user.

        :return: A Profile object containing the user's profile information or None if an error occurs.
        """
        query_parameters = {
            "operationName": "profileAttributes",
            "variables": json.dumps({}),
            "extensions": json.dumps(
                {
                    "persistedQuery": {
                        "version": 1,
                        "sha256Hash": "53bcb064f6cd18c23f752bc324a791194d20df612d8e1239c735144ab0399ced",
                    }
                }
            ),
        }

        encoded_query = urlencode(query_parameters)

        url = f"pathfinder/v1/query?{encoded_query}"

        try:
            response = self._make_request(url)
            profile_data = response.get("data", {}).get("me", {}).get("profile", {})
            if not profile_data:
                raise ValueError("Invalid profile data received.")
            return Profile(
                avatar=profile_data.get("avatar"),
                avatar_background_color=profile_data.get("avatarBackgroundColor"),
                name=profile_data.get("name", ""),
                uri=profile_data.get("uri", ""),
                username=profile_data.get("username", ""),
            )

        except Exception as e:
            print(f"An error occurred while fetching profile attributes: {e}")
            return None

    def get_account_attributes(self) -> Optional[AccountAttributes]:
        """
        Fetch the account attributes of the authenticated Spotify user.

        :return: An AccountAttributes object containing the user's account information or None if an error occurs.
        """
        # Define the query parameters
        query_parameters = {
            "operationName": "accountAttributes",
            "variables": json.dumps({}),  # Empty variables for this query
            "extensions": json.dumps(
                {
                    "persistedQuery": {
                        "version": 1,
                        "sha256Hash": "4fbd57be3c6ec2157adcc5b8573ec571f61412de23bbb798d8f6a156b7d34cdf",
                    }
                }
            ),
        }

        # Encode the query parameters
        encoded_query = urlencode(query_parameters)

        # API endpoint
        url = f"pathfinder/v1/query?{encoded_query}"

        try:
            # Perform the request
            response = self._make_request(url)

            # Extract and validate the account data
            account_data = response.get("data", {}).get("me", {}).get("account", {})
            attributes = account_data.get("attributes", {})
            if (
                not attributes
                or not account_data.get("country")
                or not account_data.get("product")
            ):
                raise ValueError("Invalid account data received.")

            # Map the response to the AccountAttributes class
            return AccountAttributes(
                catalogue=attributes.get("catalogue", ""),
                dsa_mode_available=attributes.get("dsaModeAvailable", False),
                dsa_mode_enabled=attributes.get("dsaModeEnabled", False),
                multi_user_plan_current_size=attributes.get("multiUserPlanCurrentSize"),
                multi_user_plan_member_type=attributes.get("multiUserPlanMemberType"),
                on_demand=attributes.get("onDemand", False),
                opt_in_trial_premium_only_market=attributes.get(
                    "optInTrialPremiumOnlyMarket", False
                ),
                country=account_data.get("country", ""),
                product=account_data.get("product", ""),
            )

        except Exception as e:
            print(f"An error occurred while fetching account attributes: {e}")
            return None
