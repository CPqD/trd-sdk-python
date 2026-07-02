# -*- coding: utf-8 -*-
"""
File with wrappers for the transcription server REST API.

Created on Thu Nov 29 09:18:03 2018

@author: valterf
"""
import requests
import time
import logging
import urllib
import json
from datetime import datetime
from typing import List, Dict, Optional
from contextlib import closing


class TranscriptionApi:
    """Class which pre-tests the REST HTTP URL and wraps all requests."""

    class TimeoutException(Exception):
        """Timeout exception for the Transcription REST API."""

    def __init__(
        self,
        url: str,
        username: str = "",
        password: str = "",
        retry: int = 60,
        retry_period: float = 2,
        sl_host=None,
        sl_port=None,
        sl_protocol="https",
        sl_token=None,
        sl_username=None,
        sl_password=None,
    ):
        self._log = logging.getLogger("cpqdtrd.api")

        i = 0
        ok = False
        self._url = url
        self._sl_host = sl_host
        self._sl_port = sl_port
        self._sl_protocol = sl_protocol
        self._sl_username = sl_username
        self._sl_password = sl_password

        if sl_token:
            self._sl_token = sl_token
            self._token_expiration = None
        else:
            self._sl_token, self._token_expiration = self.create_token()

        if self._sl_token:
            self._headers = {"Authorization": "Bearer " + self._sl_token}
        else:
            self._headers = {}

        if username and password:
            self._auth = requests.auth.HTTPBasicAuth(username, password)
        else:
            self._auth = None

        while not ok:
            try:
                for r in self.query():
                    self._log.debug("response: {}".format(r))
                ok = True
            except Exception as e:
                self._log.warning("Exception on API list request: {}".format(e))
                self._log.warning("Retry {} of {}".format(i, retry))
                time.sleep(retry_period)
                i += 1
                if i > retry:
                    msg = "API call retries exceeded"
                    raise self.TimeoutException(msg)

    def create(
        self,
        file_path: str,
        tag: str = None,
        config: List[str] = None,
        callbacks_url: List = [],
    ):
        self.check_token_expiration()

        upload_request = "{}/job/create".format(self._url)
        if tag:
            upload_request += "?tag={}".format(tag)

        data = {}
        if config:
            data["config"] = config

        if len(callbacks_url) > 0:
            data["callback_urls"] = ",".join(callbacks_url)

        with open(file_path, "rb") as f:
            upload_file = [("upload_file", f)]
            return requests.post(
                upload_request,
                data=data,
                files=upload_file,
                auth=self._auth,
                headers=self._headers,
            )

    def list_jobs(self, page: int = 1, limit: int = 100, tag: str = None):
        self.check_token_expiration()

        params = {"page": page, "limit": limit}
        if tag:
            params["tag"] = tag
        return requests.get(
            "{}/job".format(self._url),
            params=params,
            auth=self._auth,
            headers=self._headers,
        )

    def status(self, job_id: str):
        self.check_token_expiration()
        return requests.get(
            "{}/job/status/{}".format(self._url, job_id),
            auth=self._auth,
            headers=self._headers,
        )

    def result(self, job_id: str):
        self.check_token_expiration()
        return requests.get(
            "{}/job/result/{}".format(self._url, job_id),
            auth=self._auth,
            headers=self._headers,
        )

    def stop(self, job_id: str):
        self.check_token_expiration()
        return requests.post(
            "{}/job/stop/{}".format(self._url, job_id),
            auth=self._auth,
            headers=self._headers,
        )

    def retry(self, job_id: str):
        self.check_token_expiration()
        return requests.post(
            "{}/job/retry/{}".format(self._url, job_id),
            auth=self._auth,
            headers=self._headers,
        )

    def delete(self, job_id: str):
        self.check_token_expiration()
        return requests.delete(
            "{}/job/{}".format(self._url, job_id),
            auth=self._auth,
            headers=self._headers,
        )

    def query(
        self,
        tags: List[str] = [],
        filenames: List[str] = [],
        statuses: List[str] = [],
        projection: List[str] = [],
        get_result: bool = False,
        page: int = 1,
        limit: int = 100,
        start_date: datetime = None,
        end_date: datetime = None,
    ):
        self.check_token_expiration()
        request = "{}/query/job".format(self._url)

        params = {}
        if tags:
            params["tag"] = tags
        if filenames:
            params["filenames"] = filenames
        if statuses:
            params["status"] = statuses
        if projection:
            params["projection"] = projection
        if get_result:
            params["result"] = "true"

        params["page"] = page
        params["limit"] = limit

        if start_date:
            params["start_date"] = start_date.isoformat()
        if end_date:
            params["end_date"] = end_date.isoformat()

        with closing(
            requests.get(
                request,
                params=params,
                stream=True,
                auth=self._auth,
                headers=self._headers,
            )
        ) as r:
            for line in r.iter_lines():
                yield line

    def webhook_whoami(self):
        self.check_token_expiration()
        whoami_request = "{}/webhook/whoami".format(self._url)
        return requests.get(whoami_request, auth=self._auth, headers=self._headers)

    def webhook_validate(
        self,
        host: str,
        port: Optional[int] = None,
        timeout: Optional[int] = None,
        retries: Optional[int] = None,
        token: str = "",
        crt: str = "",
    ):
        self.check_token_expiration()
        test_request = "{}/webhook/validate".format(self._url)
        webhook_url = host
        if port is not None:
            webhook_url += ":{}".format(port)
        payload = {"url": webhook_url}
        if timeout:
            payload["timeout"] = int(timeout)
        if retries:
            payload["retries"] = int(retries)
        if crt is not None or token is not None:
            r = requests.post(
                test_request,
                params=payload,
                auth=self._auth,
                json={"crt": crt, "token": token},
                headers=self._headers,
            )
        else:
            r = requests.get(
                test_request, params=payload, auth=self._auth, headers=self._headers
            )
        return r

    def create_token(self):
        if None not in (
            self._sl_host,
            self._sl_port,
            self._sl_username,
            self._sl_password,
            self._sl_protocol
        ):
            request = requests.post(
                url="{}://{}:{}/auth/token".format(self._sl_protocol, self._sl_host, self._sl_port),
                auth=(self._sl_username, self._sl_password),
                timeout=10,
            )
            if request.status_code == 200:
                access_token = request.json()["access_token"]
                token_expiration = int(request.json()["expires_in"]) + int(time.time())
                return access_token, token_expiration
            request.raise_for_status()
        return None, None

    def check_token_expiration(self):
        if self._token_expiration:
            if time.time() >= self._token_expiration:
                self._sl_token, self._token_expiration = self.create_token()
                self._headers = {"Authorization": "Bearer " + self._sl_token}
