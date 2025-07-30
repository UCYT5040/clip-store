from datetime import datetime, UTC, timedelta
from os import makedirs, getenv
from random import randrange
from threading import Thread
from time import sleep
from xml.etree import ElementTree

from cv2 import destroyAllWindows, imwrite, VideoCapture
from glocaltokens.client import GLocalAuthenticationTokens
from gpsoauth import perform_oauth
from isodate import parse_duration
from requests import get


class Nest:
    FETCH_INTERVAL = 60 * 1  # Every 1 minute

    def __init__(self, max_workers=4):
        self.g = GLocalAuthenticationTokens(
            master_token=getenv("GOOGLE_TOKEN"),
            username=getenv("GOOGLE_EMAIL"),
            password="password"
        )
        self.cached_home_data = None
        self.mac_address = None
        self.access_token = None
        self.access_token_fetched_at = None
        self.last_fetched = None
        self._load_last_fetched()
        self._fetch_thread = Thread(target=self._fetch_loop, daemon=True)
        self._fetch_thread.start()

    def _fetch_loop(self):
        while True:
            now = datetime.now(UTC)
            if (self.last_fetched is None or
                    now - self.last_fetched > timedelta(seconds=self.FETCH_INTERVAL)
            ):
                print("Fetching new data...")
                for device in self.get_home_data().get("devices", []):
                    device_id = device.get("id")
                    if device_id:
                        print(f"Fetching missing video for device {device_id}")
                        self._get_missing_video(device_id)
                print("Finished fetching data.")
                self._save_last_fetched()
            else:
                sleep_duration = self.FETCH_INTERVAL - (now - self.last_fetched).total_seconds()
                print(f"Sleeping for {sleep_duration} seconds until next fetch.")
                sleep(self.FETCH_INTERVAL - (now - self.last_fetched).total_seconds())

    def _load_last_fetched(self):
        try:
            with open("last_fetched.txt", "r") as f:
                self.last_fetched = datetime.fromisoformat(f.read().strip())
        except FileNotFoundError:
            self.last_fetched = datetime.now(UTC) - timedelta(hours=1)
        except ValueError:
            self.last_fetched = datetime.now(UTC) - timedelta(hours=1)
        return self.last_fetched

    def _save_last_fetched(self):
        self.last_fetched = datetime.now(UTC)
        with open("last_fetched.txt", "w") as f:
            f.write(self.last_fetched.isoformat())

    def _generate_mac_address(self):
        mac_string = "".join(
            [f"{randrange(16):x}" for _ in range(16)]
        )
        return mac_string

    def _get_mac_address(self):
        if self.mac_address is None:
            self.mac_address = self._generate_mac_address()
        return self.mac_address

    def _get_homegraph_data(self):
        res = self.g.get_homegraph()
        if not res:
            return {"error": "No home data found"}
        response = {
            "home": res.home.home_name,
            "address": res.home.location.address,
            "devices": []
        }
        for device in res.home.devices:
            if device.device_type == "action.devices.types.CAMERA":
                response["devices"].append({
                    "name": device.device_name.strip(),
                    "id": device.device_info.agent_info.unique_id
                })
            else:
                print(f"Skipping device {device.device_name} of type {device.device_type}")
        return response

    def get_home_data(self):
        if self.cached_home_data is None or 'error' in self.cached_home_data:
            self.cached_home_data = self._get_homegraph_data()
        return self.cached_home_data

    def _fetch_access_token(self):
        # Cannot use GLocalAuthenticationTokens here as it returns a HomeGraph token, not a Nest token
        # Instead, manually request the access token
        res = perform_oauth(
            getenv("GOOGLE_EMAIL"),
            getenv("GOOGLE_TOKEN"),
            self._get_mac_address(),
            app="com.google.android.apps.chromecast.app",
            service="oauth2:https://www.googleapis.com/auth/nest-account",
            client_sig="24bb24c05e47e0aefa68a58a766179d9b613a600"
        )
        return res["Auth"]

    def _get_access_token(self):
        now = datetime.now(UTC)
        if (
                self.access_token is None or
                self.access_token_fetched_at is None or
                (now - self.access_token_fetched_at) > timedelta(minutes=5)
        ):
            self.access_token = self._fetch_access_token()
            self.access_token_fetched_at = now
            print("Fetched new access token:", self.access_token)
        return self.access_token

    def _get_events_between(self, start: datetime, end: datetime, device_id: str):
        print("ATT ___", self._get_access_token())
        res = get(
            f"https://nest-camera-frontend.googleapis.com/dashmanifest/namespace/nest-phoenix-prod/device/{device_id}",
            params={
                "start_time": start.isoformat()[:-9] + "Z",
                "end_time": end.isoformat()[:-9] + "Z",
                "types": 4,
                "variant": 2
            },
            headers={
                "Authorization": f"Bearer {self._get_access_token()}",
            }
        )
        return res.text

    def _get_missing_video(self, device_id: str):
        end_time = datetime.now(UTC)
        start_time = self.last_fetched or end_time - timedelta(hours=1)
        print(start_time, end_time)
        event_data = self._get_events_between(start_time, end_time, device_id)
        print(event_data)
        root = ElementTree.fromstring(event_data)
        periods = root.findall(".//{urn:mpeg:dash:schema:mpd:2011}Period")
        for period in periods:
            event_start_time = datetime.fromisoformat(period.attrib['programDateTime'])
            duration = min(timedelta(seconds=30), parse_duration(period.attrib['duration']))
            event_end_time = event_start_time + duration
            print(f"Event from {event_start_time.timestamp() * 1000} to {event_end_time.timestamp() * 1000}")
            res = get(
                f"https://nest-camera-frontend.googleapis.com/mp4clip/namespace/nest-phoenix-prod/device/{device_id}",
                params={
                    "start_time": int(event_start_time.timestamp() * 1000),
                    "end_time": int(event_end_time.timestamp() * 1000),
                },
                headers={
                    "Authorization": f"Bearer {self._get_access_token()}",
                }
            )
            makedirs(f"clips/{device_id}", exist_ok=True)
            with open(f"clips/{device_id}/{start_time.timestamp()}.mp4", "wb") as f:
                f.write(res.content)
            with open(f"clips/{device_id}/{start_time.timestamp()}.txt", "w") as f:
                f.write(f"{event_start_time.timestamp()}\n")
                f.write(f"{event_end_time.timestamp()}")

            # Save a thumbnail
            video_path = f"clips/{device_id}/{start_time.timestamp()}.mp4"
            cap = VideoCapture(video_path)
            if cap.isOpened():
                ret, frame = cap.read()
                if ret:
                    thumbnail_path = f"clips/{device_id}/{start_time.timestamp()}.jpg"
                    imwrite(thumbnail_path, frame)
                    print(f"Saved thumbnail to {thumbnail_path}")
                else:
                    print(f"Failed to read frame from {video_path}")
            else:
                print(f"Failed to open video file {video_path}")
            cap.release()
            destroyAllWindows()
