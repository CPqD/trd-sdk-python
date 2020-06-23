# -*- coding: utf-8 -*-
"""
Created on Tue Nov 13 11:14:59 2018

@author: valterf
"""
from .api import TranscriptionApi
from .cert import create_self_signed_cert

from bson.json_util import loads, ObjectId
from flask import Flask, request
from gevent.pywsgi import WSGIServer
from gevent.event import Event
import soundfile as sf

from collections import defaultdict as dd
import ipaddress
import logging
import numbers
import shutil
import tempfile
import uuid


class TranscriptionClient:
    def __init__(
        self,
        api_url,
        webhook_port=8443,
        webhook_host=None,
        webhook_listener="0.0.0.0",
        webhook_protocol="https",
        username=None,
        password=None,
        cert_path=None,
        key_path=None,
        **flask_kwargs
    ):
        self._result_events = dd(dict)  # Event variable dict

        self._flask_kwargs = flask_kwargs
        self.api = TranscriptionApi(
            api_url, username=username, password=password
        )

        if webhook_host is not None:
            self._webhook_host = webhook_host
        else:
            self._webhook_host = self.api.webhook_whoami().json()
        self._webhook_port = webhook_port
        self._webhook_listener = webhook_listener
        self._webhook_protocol = webhook_protocol

        if cert_path is None and key_path is None:
            self._cert_dir = tempfile.mkdtemp()
            self._cert_path = "{}/cert".format(self._cert_dir)
            self._key_path = "{}/key".format(self._cert_dir)
        elif cert_path is None or key_path is None:
            raise ValueError("cert_path and key_path must be set together!")
        else:
            self._cert_dir = None
            self._crt = None
            self._cert_path = cert_path
            self._key_path = key_path

        self._log = logging.getLogger(self.__class__.__name__)
        self._callbacks = {}

        self._http_server = None

        self._reset_start()

    def _reset_start(self):
        """Start the Flask app and the WSGI server."""
        if self._http_server is not None:
            self._http_server.stop()

        self._app = Flask("cpqdtrd", **self._flask_kwargs)

        @self._app.route("/<audio_id>", methods=["POST"])
        def root_callback(audio_id):
            # Root callback is only responsible for signaling that the audiofile will
            # no longer be processed - either by finished, failed, reset or deleted
            # states.
            result = request.json
            if "token" not in result or result["token"] != self._validation_token:
                raise ValueError("Invalid token")
            if (
                audio_id in self._result_events
                and "__root__" in self._result_events[audio_id]
            ):
                self._result_events[audio_id]["__root__"].set()
                del self._result_events[audio_id]["__root__"]
                if not self._result_events[audio_id]:
                    del self._result_events[audio_id]
            return "OK", 200

        for name, callback in list(self._callbacks.items()):
            self.register_callback(callback, name)

        if self._webhook_protocol == "http":
            self._http_server = WSGIServer(
                (self._webhook_listener, self._webhook_port),
                self._app,
                log=logging.getLogger("WSGIServer"),
                error_log=logging.getLogger("WSGIError"),
                do_handshake_on_connect=False,
            )
        elif self._webhook_protocol == "https":
            # Create certificate and private key
            if self._cert_dir is not None:
                create_self_signed_cert(
                    self._webhook_host, self._cert_path, self._key_path
                )
                with open(self._cert_path, "r") as f:
                    self._crt = f.read()
            self._http_server = WSGIServer(
                (self._webhook_listener, self._webhook_port),
                self._app,
                certfile=self._cert_path,
                keyfile=self._key_path,
                log=logging.getLogger("WSGIServer"),
                error_log=logging.getLogger("WSGIError"),
                do_handshake_on_connect=False,
            )
        else:
            raise ValueError("Invalid protocol: {}".format(self._webhook_protocol))

        self._http_server.start()
        self._validation_token = str(uuid.uuid4())
        if not self.api.webhook_validate(
            self._webhook_host,
            self._webhook_port,
            crt=self._crt,
            token=self._validation_token,
        ).json():
            raise ConnectionError(
                "{}:{} not reachable by the transcription server".format(
                    self._webhook_host, self._webhook_port
                )
            )

    def __del__(self):
        self.stop()

    def stop(self):
        if self._http_server is not None:
            self._http_server.stop()
        if self._cert_dir is not None:
            shutil.rmtree(self._cert_dir)

    def register_callback(self, callback, name=None):
        """Register a callback with optional name."""
        if name is None:
            name = "_callback_{}".format(len(self._callbacks))
        elif name[:9] == "_callback":
            raise ValueError("Prefix _callback is reserved for callback names!")

        self._callbacks[name] = callback

        # Oddly, Flask does not require server restart for adding new endpoints, so
        # we do it while the WSGI is still up.
        # Instead of using the decorator, we explicitly use the add_url_rule method to
        # avoid endpoint name collision.
        def new_callback(audio_id):
            try:
                r = request.json
                if "token" not in r or r["token"] != self._validation_token:
                    raise ValueError("Invalid token")
                callback(audio_id, r)
            except Exception:
                raise
            finally:  # Emit events regardless of the success of the callback op
                if (
                    audio_id in self._result_events
                    and name in self._result_events[audio_id]
                ):
                    self._result_events[audio_id][name].set()
                    del self._result_events[audio_id][name]
                    if not self._result_events[audio_id]:
                        del self._result_events[audio_id]

            # Return status only if successful, so that any callback errors are
            # logged in the transcription server.
            return "OK", 200

        self._app.add_url_rule(
            "/{}/<audio_id>".format(name), name, new_callback, methods=["POST"]
        )

    def unregister_callback(self, *callback_names):
        """Unregister one or more named callbacks."""
        names = []
        for name in callback_names:
            if type(name) is int:
                name = "_callback_{}".format(name)
            elif type(name) is not str:
                raise ValueError("{} not a string!".format(name))
            names.append(name)
        for name in names:
            if name in self._callbacks:
                del self._callbacks[name]
            else:
                self._log.warning("Callback {} not registered".format(name))

        # There's no way to remove endpoints in Flask. Therefore, we need to restart
        # the server while re-regestring the remaining callbacks
        self._reset_start()

    def unregister_all(self):
        """Unregister all callbacks."""
        for name in list(self._callbacks.keys()):
            del self._callbacks[name]
        self._reset_start()

    def transcribe(self, path, timeout="auto", delete_after=True):
        """
        Transcribe an audio file.

        The blocking transcribe operation (timeout >=0) does not guarantee the
        execution of all callbacks. Each callback should have its own event
        operations.

        Parameters
        ----------
        path : str
            Path of the audio file.
        timeout : str or float, optional
            Sets a timeout (in seconds) fot the result operation

            If < 0, starts transcription and returns promptly only with the audio_id

            If == 0, waits indefinitely

            If 'auto', the timeout is set as the max between 30 and the audio length
            in seconds.

            Default: 'auto'
        delete_after : bool, optional
            Whether the results are deleted on the server after processed.
            Only meaningful if timeout < 0, otherwise it should be passed to
            the wait_result method.

            Default: True

        Returns
        -------
        Only the audio id if timeout < 0, or a tuple (audio_id: str, result: dict)
        """
        if timeout == "auto":
            with sf.SoundFile(path) as f:
                timeout = len(f) / f.samplerate
            timeout = max(30, timeout)
        elif not isinstance(timeout, numbers.Number):
            raise ValueError("Invalid value for timeout: {}".format(timeout))

        # Upload audio file. Currently only expects
        r = self.api.audiofile_upload(path)
        r.raise_for_status()
        audio_id = next(iter(r.json().values())).split("/")[-1]
        if not ObjectId.is_valid(audio_id):
            raise ValueError(audio_id)

        # Set webhooks in the request
        webhook_root = "{}://{}:{}".format(
            self._webhook_protocol, self._webhook_host, self._webhook_port
        )
        webhooks = [webhook_root]
        webhooks += ["{}/{}".format(webhook_root, name) for name in self._callbacks]

        # Init events and start transcription. Return audio_id if timeout < 0
        self._result_events[audio_id]["__root__"] = Event()
        for name in self._callbacks:
            self._result_events[audio_id][name] = Event()
        self.api.transcription_start(audio_id, request_args={"webhook": webhooks})
        if timeout < 0:
            return audio_id
        return audio_id, self.wait_result(audio_id, timeout, delete_after)

    def wait_result(self, audio_id, timeout=0, delete_after=True):
        """
        Wait for the result of an audio file.

        If callbacks are set, also waits for all callbacks to finish.

        Parameters
        ----------
        audio_id : str
            The ID of the audio file to wait for.
        timeout : float, optional (in seconds)
            Sets a timeout (in seconds) for the result operation.

            If < 0, returns if completed, otherwise returns False

            If == 0, waits indefinitely

            Default: 0
        delete_after : bool, optional
            Whether the results are deleted on the server after obtaining the result.

            Default: True
        Returns
        -------
        The transcription result as a dict or False if timeout < 0 and not completed.
        """
        if audio_id in self._result_events:
            if timeout > 0:
                for event in list(self._result_events[audio_id].values()):
                    if not event.wait(timeout):
                        return False
            elif timeout < 0:
                return False
            else:
                for event in list(self._result_events[audio_id].values()):
                    event.wait()
        result = self.api.transcription_result(audio_id).json()
        if delete_after:
            self.api.audiofile_delete(audio_id)
        return result
