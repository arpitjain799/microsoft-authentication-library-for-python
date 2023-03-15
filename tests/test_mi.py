import json
import os
import time
import unittest
try:
    from unittest.mock import patch, ANY
except:
    from mock import patch, ANY
import requests

from tests.http_client import MinimalResponse
from msal import TokenCache, ManagedIdentity


class ManagedIdentityTestCase(unittest.TestCase):
    maxDiff = None

    def _test_token_cache(self, app):
        cache = app._token_cache._cache
        self.assertEqual(1, len(cache.get("AccessToken", [])), "Should have 1 AT")
        at = list(cache["AccessToken"].values())[0]
        self.assertEqual(
            app._client_id or "SYSTEM_ASSIGNED_MANAGED_IDENTITY",
            at["client_id"],
            "Should have expected client_id")
        self.assertEqual("managed_identity", at["realm"], "Should have expected realm")


class VmTestCase(ManagedIdentityTestCase):

    def test_happy_path(self):
        app = ManagedIdentity(requests.Session(), token_cache=TokenCache())
        with patch.object(app._http_client, "get", return_value=MinimalResponse(
            status_code=200,
            text='{"access_token": "AT", "expires_in": "1234", "resource": "R"}',
        )) as mocked_method:
            result = app.acquire_token("R")
            mocked_method.assert_called_once()
            self.assertEqual({
                "access_token": "AT",
                "expires_in": 1234,
                "resource": "R",
                "token_type": "Bearer",
            }, result, "Should obtain a token response")
            self.assertEqual(
                result["access_token"], app.acquire_token("R").get("access_token"),
                "Should hit the same token from cache")
            self._test_token_cache(app)

    def test_vm_error_should_be_returned_as_is(self):
        raw_error = '{"raw": "error format is undefined"}'
        app = ManagedIdentity(requests.Session(), token_cache=TokenCache())
        with patch.object(app._http_client, "get", return_value=MinimalResponse(
            status_code=400,
            text=raw_error,
        )) as mocked_method:
            self.assertEqual(json.loads(raw_error), app.acquire_token("R"))
            self.assertEqual({}, app._token_cache._cache)


@patch.dict(os.environ, {"IDENTITY_ENDPOINT": "http://localhost", "IDENTITY_HEADER": "foo"})
class AppServiceTestCase(ManagedIdentityTestCase):

    def test_happy_path(self):
        # TODO: Combine this with VM's test case, and move it into base class
        app = ManagedIdentity(requests.Session(), token_cache=TokenCache())
        now = int(time.time())
        with patch.object(app._http_client, "get", return_value=MinimalResponse(
            status_code=200,
            text='{"access_token": "AT", "expires_on": "%s", "resource": "R"}' % (now + 100),
        )) as mocked_method:
            result = app.acquire_token("R")
            mocked_method.assert_called_once()
            self.assertEqual({
                "access_token": "AT",
                "expires_in": 100,
                "resource": "R",
                "token_type": "Bearer",
            }, result, "Should obtain a token response")
            self.assertEqual(
                result["access_token"], app.acquire_token("R").get("access_token"),
                "Should hit the same token from cache")
            self._test_token_cache(app)

    def test_app_service_error_should_be_normalized(self):
        raw_error = '{"statusCode": 500, "message": "error content is undefined"}'
        app = ManagedIdentity(requests.Session(), token_cache=TokenCache())
        with patch.object(app._http_client, "get", return_value=MinimalResponse(
            status_code=500,
            text=raw_error,
        )) as mocked_method:
            self.assertEqual({
                "error": "invalid_scope",
                "error_description": "500, error content is undefined",
            }, app.acquire_token("R"))
            self.assertEqual({}, app._token_cache._cache)

