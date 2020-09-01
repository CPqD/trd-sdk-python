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
from typing import List, Dict, Union
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
                self.query()
                ok = True
            except Exception as e:
                self._log.warning("Exception on API list request: {}".format(e))
                self._log.warning("Retry {} of {}".format(i, retry))
                time.sleep(retry_period)
                i += 1
                if i > retry:
                    msg = "API call retries exceeded"
                    raise self.TimeoutException(msg)

    def upload(self, file_path: str, tag: str = None, config: List[str] = None, callbacks_url: List = []):
        upload_request = "{}/job/upload/".format(self._url)
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

    def status(self, job_id: str):
        return requests.get("{}/job/status/{}".format(self._url, job_id), auth=self._auth)

    def result(self, job_id: str):
        return requests.get("{}/job/result/{}".format(self._url, job_id), auth=self._auth)

    def stop(self, job_id: str):
        return requests.post("{}/job/stop/{}".format(self._url, job_id), auth=self._auth)

    def retry(self, job_id: str):
        return requests.post("{}/job/retry/{}".format(self._url, job_id), auth=self._auth)

    def delete(self, job_id: str):
        return requests.delete("{}/job/delete/{}".format(self._url, job_id), auth=self._auth)

    def query(
        self,
        tags: List[str] = [],
        filenames: List[str] = [],
        statuses: List[str] = [],
        projection: List[str] = [],
        get_result: bool = False,
        page: int = 1,
        page_size: int = 100,
    ):
        request = "{}/job/?".format(self._url)

        for tag in tags:
            request += "&tag={}".format(tag)
        for filename in filenames:
            request += "&filename={}".format(filename)
        for status in statuses:
            request += "&status={}".format(status)

        if get_result:
            request += "&result=True"

        # projection
        assert(isinstance(projection, list))
        for p in projection:
            request += "&projection={}".format(p)

        request += "&page={}&page_size={}".format(page, page_size)

        with closing(requests.get(request, stream=True, auth=self._auth)) as r:
            for line in r.iter_lines():
                yield line

    def query_pages(self, **kwargs):
        next_page = True
        n = 1
        while next_page:
            for _page in self.query(page=n, page_size=100, **kwargs):
                n += 1
                if len(_page) > 2:
                    yield json.loads(_page)
                else:
                    next_page = False

    def webhook_whoami(self):
        whoami_request = "{}/webhook/whoami".format(self._url)
        return requests.get(whoami_request, auth=self._auth)

    def webhook_validate(
        self,
        host: str,
        port: int,
        timeout: Union[None, int] = None,
        retries: Union[None, int] = None,
        token: str = "",
        crt: str = "",
    ):
        test_request = "{}/webhook/validate".format(self._url)
        payload = {
            "url": "{}:{}".format(host, port)
        }
        if timeout:
            payload["timeout"] = int(timeout)
        if retries:
            payload["retries"] = int(retries)

        if crt is not None:
            r = requests.post(
                test_request, params=payload, auth=self._auth, json={"crt": crt, "token": token}
            )
        else:
            r = requests.get(test_request, params=payload, auth=self._auth)
        return r
