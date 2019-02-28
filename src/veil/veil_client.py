"""
Client for interacting with veil.co API

author: officialcryptomaster@gmail.com
"""
from typing import NamedTuple
import logging
import requests
from veil.constants import NETWORK_INFO
from utils.zeroexutils import ZeroExWeb3Client
from utils.logutils import setup_logger


LOGGER = setup_logger(__name__, log_level=logging.DEBUG)


class MarketStatus(NamedTuple):  # pylint: disable=too-few-public-methods
    """MarketStatus value strings"""
    OPEN = "open"
    RESOLVED = "resolved"


class TokenType(NamedTuple):  # pylint: disable=too-few-public-methods
    """TokenType value strings"""
    LONG = "long"
    SHORT = "short"


class VeilClient(ZeroExWeb3Client):
    """Client for interacting with veil.co API"""

    __name__ = "VeilClient"

    def __init__(
        self,
        network_id,
        web3_rpc_url,
        private_key=None,
    ):
        """Create an instance of VeilClient to interact with the veil.co API

        Keyword arguments:
        network_id -- numerable id of networkId convertible to `constants.NetworkId`
        web3_rpc_url -- string of the URL of the Web3 service
        private_key -- hex bytes or hex string of private key for signing transactions
            (must be convertible to `HexBytes`) (default: None)
        """
        super(VeilClient, self).__init__(
            network_id=network_id,
            web3_rpc_url=web3_rpc_url,
            private_key=private_key,
        )
        self._veil_api_url = NETWORK_INFO[self.network_id]["veil_api_url"]
        # cache markets by filter tuple
        self._markets = {}

    @staticmethod
    def _request_get(
        url,
        params=None,
        res_is_json=True,
        raise_on_error=True,
    ):
        """Helper function for handling get requests

        Keyword arguments:
        url -- full path to endpoint
        params -- dictionary of parameters for endpoint (default: None)
        res_is_json -- boolean of whether expected result is json
            (default: True)
        raise_on_error -- boolean of whether should raise exception if there
            is an error (default: True)
        """
        params = params or {}
        LOGGER.debug("sending request url=%s with params=%s", url, params)
        res = requests.get(url, params)
        if res.status_code != 200:
            LOGGER.error(
                "Failed with status_code=%s in url=%s with params=%s",
                res.status_code, url, params)
            try:
                error_msg = res.json()
                LOGGER.error(error_msg)
            except Exception as ex:  # pylint: disable=broad-except
                LOGGER.exception(
                    "error was not a valid json: %s", res)
                if raise_on_error:
                    raise ex
            if raise_on_error:
                raise Exception(error_msg)
        if res_is_json:
            try:
                res = res.json()
            except Exception as ex:  # pylint: disable=broad-except
                LOGGER.exception(
                    "result with status_code=%s was not a valid json",
                    res.status_code
                )
                if raise_on_error:
                    raise ex
        return res

    def _request_get_paginated(
        self,
        url,
        params=None,
        page=None,
        per_page=20,
        raise_on_error=True,
    ):
        """ Helper function for handling get requests with pagination

        Keyword arguments:
        url -- full path to endpoint
        params -- dictionary of parameters for endpoint (default: None)
        page -- interger page number to get results from. Note that first page
            is at page=0 (default: None which means get all pages)
        per_page -- interger number of records per page (default: 20 but only
            honored if a valid `page` is passed in)
        raise_on_error -- boolean of whether should raise exception if there
            is an error (default: True)
        """
        params = params or {}
        res = []
        if page is not None and page > -1:
            next_page = page
        else:
            next_page = 0  # pages start at 0
        while True:
            params["page"] = next_page
            params["pageSize"] = per_page
            this_res = self._request_get(
                url, params, raise_on_error=raise_on_error)
            if not this_res:
                break
            this_data = this_res["data"]
            this_res = this_data["results"]
            if not this_res:
                break
            res.extend(this_res)
            tot_pages = int(this_data["total"])
            if page is not None or len(res) == tot_pages:
                break
            next_page = next_page + 1
        return res

    def get_markets(
        self,
        channel=None,
        status=None,
        page=None,
        per_page=20,
        force_refresh=False,
    ):
        """Fetch list of markets optionally filterd on channel or status
        Note: Public endpoint, does not need an account

        Keyword arguments:
        channel -- str from of channel for filtering
            (default: None which means no filtering based on channel)
        status -- str from `MarketStatus` enum for filtering
            (default: None which means no filtering based on status)
        page -- interger page number to get results from. Note that first page
            is at page=0 (default: None which means get all pages)
        per_page -- interger number of records per page (default: 20 but only
            honored if a valid `page` is passed in)
        force_refresh -- boolean of whether results should be fetched again
            from server or from in-memory cache (default: False)
        """
        if not force_refresh and self._markets is not None:
            _markets = self._markets.get((channel, status, page, per_page))
            if _markets is not None:
                return _markets
        params = {}
        if channel:
            params["channel"] = channel
        if status:
            params["status"] = status
        _markets = self._request_get_paginated(
            url="{}{}".format(self._veil_api_url, "markets"),
            params=params,
            page=page,
            per_page=per_page,
        )
        self._markets[(channel, status, page, per_page)] = _markets
        return _markets

    def get_market(
        self,
        market_slug,
        force_refresh=False,
    ):
        """Fetch a single market using the market "slug" identifier
        Note: Public endpoint, does not need an account

        Keyword arguments:
        market_slug -- string "slug" (relatively short human-readable identifier)
            from /markets API call
        force_refresh -- boolean of whether results should be fetched again
            from server or from in-memory cache (default: False)
        """
        if not force_refresh and self._markets is not None:
            _markets = self._markets.get(market_slug)
            if _markets is not None:
                return _markets
        _market = self._request_get(
            url="{}{}/{}".format(self._veil_api_url, "markets", market_slug),
        )["data"]
        self._markets[market_slug] = _market
        return _market
