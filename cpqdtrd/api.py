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
    ):
        i = 0
        ok = False
        self._url = url

        if username and password:
            self._auth = requests.auth.HTTPBasicAuth(username, password)
        else:
            self._auth = None

        self._log = logging.getLogger("cpqdtrd.api")
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

    def create(self, file_path: str, tag: str = None, config: List[str] = None, callbacks_url: List = []):
        upload_request = "{}/job/create".format(self._url)
        if tag:
            upload_request += "?tag={}".format(tag)

        data = {}
        if config:
            data["config"] = config

        if len(callbacks_url) > 0:
            data["callback_urls"] = ','.join(callbacks_url)

        with open(file_path, "rb") as f:
            upload_file = [("upload_file", f)]
            return requests.post(
                upload_request, data=data, files=upload_file, auth=self._auth
            )

    def list_jobs(self, page: int = 1, limit: int = 100, tag: str = None):
        params = {"page": page, "limit": limit}
        if tag:
            params["tag"] = tag
        return requests.get("{}/job".format(self._url), params=params, auth=self._auth)

    def status(self, job_id: str):
        return requests.get("{}/job/status/{}".format(self._url, job_id), auth=self._auth)

    def result(self, job_id: str):
        return requests.get("{}/job/result/{}".format(self._url, job_id), auth=self._auth)

    def stop(self, job_id: str):
        return requests.post("{}/job/stop/{}".format(self._url, job_id), auth=self._auth)

    def retry(self, job_id: str):
        return requests.post("{}/job/retry/{}".format(self._url, job_id), auth=self._auth)

    def delete(self, job_id: str):
        return requests.delete("{}/job/{}".format(self._url, job_id), auth=self._auth)

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

        with closing(requests.get(request, params=params, stream=True, auth=self._auth)) as r:
            for line in r.iter_lines():
                yield line

    def webhook_whoami(self):
        whoami_request = "{}/webhook/whoami".format(self._url)
        return requests.get(whoami_request, auth=self._auth)

    def webhook_validate(
        self,
        host: str,
        port: Optional[int] = None,
        timeout: Optional[int] = None,
        retries: Optional[int] = None,
        token: str = "",
        crt: str = "",
    ):
        test_request = "{}/webhook/validate".format(self._url)
        webhook_url = host
        if port is not None:
            webhook_url += ":{}".format(port)
        payload = {
            "url": webhook_url
        }
        if timeout:
            payload["timeout"] = int(timeout)
        if retries:
            payload["retries"] = int(retries)
        if crt is not None or token is not None:
            r = requests.post(
                test_request, params=payload, auth=self._auth, json={"crt": crt, "token": token}
            )
        else:
            r = requests.get(test_request, params=payload, auth=self._auth)
        return r
