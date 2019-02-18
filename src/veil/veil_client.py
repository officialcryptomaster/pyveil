"""
Client for interacting with veil.co API

author: officialcryptomaster@gmail.com
"""
import logging
import requests
from veil.constants import NETWORK_INFO
from veil.web3utils import Web3Client
from utils.logutils import setup_logger


LOGGER = setup_logger(__name__, log_level=logging.INFO)


class VeilClient(Web3Client):
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
        self._veil_api_url = NETWORK_INFO[self._network_id]["veil_api_url"]
        # cache markets by filter tuple
        self._markets = {}

    def _request_get(
        self,
        url,
        params,
        page=None,
        per_page=20,
    ):
        """ Helper function for handling get requests with pagination

        Keyword arguments:
        url -- full path to endpoint
        params -- dictionary of parameters for endpoint
        page -- interger page number to get results from. Note that first page
            is at page=0 (default: None which means get all pages)
        per_page -- interger number of records per page (default: 20 but only
            honored if a valid `page` is passed in)
        """
        res = []
        if page is not None and page > -1:
            next_page = page
        else:
            next_page = 0  # pages start at 0
            per_page = 100
        while True:
            LOGGER.debug("sending request url=%s with params=%s", url, params)
            params["page"] = next_page
            params["pageSize"] = per_page
            this_res = requests.get(url, params)
            if this_res.status_code != 200:
                LOGGER.error(
                    "Failed with status_code=%s in url=%s with params=%s",
                    this_res.status_code, url, params)
                try:
                    LOGGER.error(this_res.json()["error"])
                except Exception:  # pylint: disable=broad-except
                    LOGGER.exception("result was not a valid json")
                if page is not None:
                    break
                next_page = page + 1
                continue

            this_data = this_res.json()["data"]
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
        """Get available markets optionally filterd on channel or status
        Note: Public endpoint, does not need an account

        Keyword arguments:
        channel -- str from `constants.VeilChannel` for filtering
            (default: None which means no filtering based on channel)
        status -- str from `constants.VeilStatus` for filtering
            (default: None which means no filtering based on status)
        """
        if not force_refresh and self._markets is not None:
            _markets = self._markets.get((channel, status))
            if _markets is not None:
                return _markets
        params = {}
        if channel:
            params["channel"] = channel
        if status:
            params["status"] = status
        _markets = self._request_get(
            url="{}{}".format(self._veil_api_url, "markets"),
            params=params,
            page=page,
            per_page=per_page,
        )
        self._markets[(channel, status)] = _markets
        return _markets
