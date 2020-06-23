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
from typing import List
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
                self.audiofile_list()
                ok = True
            except Exception as e:
                self._log.warning("Exception on API list request: {}".format(e))
                self._log.warning("Retry {} of {}".format(i, retry))
                time.sleep(retry_period)
                i += 1
                if i > retry:
                    msg = "API call retries exceeded"
                    raise self.TimeoutException(msg)

    def audiofile_list(self, batch: str = ""):
        if batch:
            return requests.get(
                "{}/audiofile/list/batch/{}".format(self._url, batch), auth=self._auth
            )
        else:
            return requests.get("{}/audiofile/list/".format(self._url), auth=self._auth)

    def audiofile_get(self, uid: str):
        return requests.get("{}/audiofile/{}".format(self._url, uid), auth=self._auth)

    def audiofile_create(self, file_name: str):
        return requests.get(
            "{}/audiofile/create/{}".format(self._url, file_name), auth=self._auth
        )

    def audiofile_create_batch(self, batch: str):
        return requests.get(
            "{}/audiofile/create/batch/{}".format(self._url, batch), auth=self._auth
        )

    def audiofile_upload(self, file_path: str, batch: str = ""):
        upload_request = "{}/audiofile/upload/".format(self._url)
        if batch:
            data = {"batch": batch}
        else:
            data = {}
        with open(file_path, "rb") as f:
            files = [("files", f)]
            return requests.post(
                upload_request, data=data, files=files, auth=self._auth
            )

    def audiofile_delete(self, uid: str, delete_on_disk: bool = False):
        delete_request = "{}/audiofile/delete/{}"
        if delete_on_disk:
            delete_request += "?deleteOnDisk=true"
        return requests.delete(delete_request.format(self._url, uid), auth=self._auth)

    def audiofile_delete_batch(self, batch: str, delete_on_disk: bool = False):
        delete_request = "{}/audiofile/delete/batch/{}"
        if delete_on_disk:
            delete_request += "?deleteOnDisk=true"
        return requests.delete(delete_request.format(self._url, batch), auth=self._auth)

    def transcription_start(self, audio_id: str, request_args: dict = {}):
        start_request = "{}/transcription/start/audiofile/{}"
        sep = "?"
        for arg, val in request_args.items():
            if arg == "webhook" and type(val) is list:
                for w in val:
                    start_request += sep
                    sep = "&"
                    start_request += "webhook={}".format(w)
            else:
                start_request += sep
                sep = "&"
                start_request += "{}={}".format(arg, val)
        return requests.get(start_request.format(self._url, audio_id), auth=self._auth)

    def transcription_start_batch(
        self, batch: str, word_hints: str = "", lm_url: str = ""
    ):
        start_request = "{}/transcription/start/batch/{}"
        sep = "?"
        if lm_url:
            start_request += sep
            sep = "&"
            start_request += "lm.uri={}".format(lm_url)
        if word_hints:
            start_request += sep
            start_request += "hints.words={}".format(word_hints)
        return requests.get(start_request.format(self._url, batch), auth=self._auth)

    def transcription_status(self, audio_id: str):
        return requests.get(
            "{}/transcription/status/audiofile/{}".format(self._url, audio_id),
            auth=self._auth,
        )

    def transcription_status_batch(self, batch: str):
        return requests.get(
            "{}/transcription/status/batch/{}".format(self._url, batch), auth=self._auth
        )

    def transcription_reset(self, audio_id: str, hard: bool = False):
        reset_request = "{}/transcription/reset/audiofile/{}"
        if hard:
            reset_request += "?hard=true"
        return requests.get(reset_request.format(self._url, audio_id), auth=self._auth)

    def transcription_reset_batch(self, batch: str, hard: bool = False):
        reset_request = "{}/transcription/reset/batch/{}"
        if hard:
            reset_request += "?hard=true"
        return requests.get(reset_request.format(self._url, batch), auth=self._auth)

    def transcription_result(self, audio_id: str, is_csv: bool = False):
        result_request = "{}/transcription/result/audiofile/{}".format(
            self._url, audio_id
        )
        if is_csv:
            result_request += "?format=csv"
        return requests.get(result_request, auth=self._auth)

    def transcription_result_batch(self, batch: str, format: str = ""):
        result_request = "{}/transcription/result/batch/{}".format(self._url, batch)
        if format != "":
            result_request += "?format=" + format
        return requests.get(result_request, auth=self._auth)

    def query_collection(self, collection: str, query: dict, project: list = []):
        query_request = "{}/query/collection/{}".format(self._url, collection)
        sep = "?"
        for k in query:
            query_request += sep + "{}={}".format(k, query[k])
            sep = "&"
        for p in project:
            query_request += sep + "project={}".format(p)
            sep = "&"
        with closing(requests.get(query_request, stream=True, auth=self._auth)) as r:
            for line in r.iter_lines():
                yield line

    def webhook_whoami(self):
        whoami_request = "{}/webhook/whoami".format(self._url)
        return requests.get(whoami_request, auth=self._auth)

    def webhook_validate(
        self, host, port, timeout=None, retries=None, token="", crt=""
    ):
        test_request = "{}/webhook/validate/{}/{}".format(self._url, host, port)
        sep = "?"
        if timeout is not None:
            test_request += sep + "timeout={}".format(timeout)
            sep = "&"
        if retries is not None:
            test_request += sep + "retries={}".format(retries)
            sep = "&"
        if crt is not None:
            return requests.post(
                test_request, auth=self._auth, json={"crt": crt, "token": token}
            )
        else:
            return requests.get(test_request, auth=self._auth)
