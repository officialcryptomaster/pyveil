"""
Client for interacting with veil.co API

author: officialcryptomaster@gmail.com
"""
from enum import Enum
import logging
import requests
from hexbytes import HexBytes
from veil.constants import NETWORK_INFO
from utils.zeroexutils import ZeroExWeb3Client
from utils.logutils import setup_logger


LOGGER = setup_logger(__name__, log_level=logging.DEBUG)


class MarketStatus(Enum):  # pylint: disable=too-few-public-methods
    """Market status value strings"""
    OPEN = "open"
    RESOLVED = "resolved"


class TokenType(Enum):  # pylint: disable=too-few-public-methods
    """Token type strings"""
    LONG = "long"
    SHORT = "short"


class OrderSide(Enum):  # pylint: disable=too-few-public-methods
    """Order side value strings"""
    BUY = "bid"
    SELL = "ask"


class OrderStatus(Enum):  # pylint: disable=too-few-public-methods
    """Order status value strings"""
    PENDING = "pending"
    OPEN = "open"
    FILLEd = "filled"
    CANCELED = "canceled"
    EXPIRED = "expired"


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
        self._session_challenge = None
        self._session = None
        # cache markets by filter tuple
        self._markets = {}

    def _str_arg_append(self):
        """String to append to list of params for `__str__`"""
        return f", authenticated={self._session is not None})"

    @property
    def session_info(self):
        """Get the session information (forces authentication if missing)"""
        if self._session is None:
            self.authenticate()
        return self._session

    @property
    def session_token(self):
        """Get the session token (forces authentication if missing)"""
        if self._session is None:
            self.authenticate()
        return self._session["token"]

    @property
    def veil_account(self):
        """Get the veil session account (forces authentication if missing"""
        if self._session is None:
            self.authenticate()
        return self._session["account"]

    def authenticate(self, force=False):
        """Get a session challenge and sign it, then use it to get a valid
        session token

        Keyword argument:
        force -- get and sign a new token regardless of whether we already
            have a valid session token
        """
        if not force and self._session:
            return self
        session_challenge_uid = self.get_session_challenge()["uid"]
        signed_session_challenge_uid = self.sign_hash(
            HexBytes(session_challenge_uid.encode("utf-8"))
        )["signature"].hex()
        self._session = self._request(
            method="POST",
            url="{}sessions".format(self._veil_api_url),
            params={
                "challengeUid": session_challenge_uid,
                "message": session_challenge_uid,
                "signature": signed_session_challenge_uid,
            },
        )["data"]
        return self

    def get_session_challenge(self):
        """Get a session challenge for authentication"""
        session_challenge = self._request(
            method="POST",
            url="{}session_challenges".format(self._veil_api_url)
        )
        self._session_challenge = session_challenge["data"]
        return self._session_challenge

    def get_markets(
        self,
        channel=None,
        status=None,
        page=None,
        per_page=None,
        force_refresh=False,
    ):
        """Fetch list of markets optionally filterd on channel or status
        Note: Public endpoint, does not need an account

        Keyword arguments:
        channel -- str from of channel for filtering
            (default: None which means no filtering based on channel)
        status -- str from `MarketStatus` enum for filtering
            (default: None which means no filtering based on status)
        page -- integer page number to get results from. Note that first page
            is at page=0 (default: None which means get all pages)
        per_page -- integer number of records per page (default: None and
            falls back to default value in `_request_paginated`)
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
        _markets = self._request_paginated(
            method="GET",
            url="{}markets".format(self._veil_api_url),
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
        _market = self._request(
            method="GET",
            url="{}markets/{}".format(self._veil_api_url, market_slug),
        )["data"]
        self._markets[market_slug] = _market
        return _market

    def get_bids(
        self,
        market_slug,
        token_type,
        page=None,
        per_page=None,
    ):
        """Fetch the long or short orders for a given market
        Note that long and short are mirror images of each other

        Keyword arguments:
        market_slug -- string "slug" (relatively short human-readable identifier)
            from /markets API call
        token_type --  value from `TokenType` enum (i.e. SHORT or LONG)
        page -- integer page number to get results from. Note that first page
            is at page=0 (default: None which means get all pages)
        per_page -- integer number of records per page (default: None and
            falls back to default value in `_request_paginated`)
        """
        if not isinstance(token_type, TokenType):
            token_type = TokenType(token_type)
        return self._request_paginated(
            method="GET",
            url="{}markets/{}/{}/bids".format(
                self._veil_api_url, market_slug, token_type.value),
            page=page,
            per_page=per_page
        )

    def get_asks(
        self,
        market_slug,
        token_type,
        page=None,
        per_page=None
    ):
        """Fetch the bids orders for a given long or short market
        Note that long and short are mirror images of each other

        Keyword arguments:
        market_slug -- string "slug" (relatively short human-readable identifier)
            from /markets API call
        token_type --  value from `TokenType` enum (i.e. SHORT or LONG)
        page -- integer page number to get results from. Note that first page
            is at page=0 (default: None which means get all pages)
        per_page -- integer number of records per page (default: None and
            falls back to default value in `_request_paginated`)
        """
        if not isinstance(token_type, TokenType):
            token_type = TokenType(token_type)
        return self._request_paginated(
            method="GET",
            url="{}markets/{}/{}/asks".format(
                self._veil_api_url, market_slug, token_type.value),
            page=page,
            per_page=per_page
        )

    def get_order_fills(
        self,
        market_slug,
        token_type,
        page=None,
        per_page=None
    ):
        """Fetch the order fill history for a given long or short market
        Note that long and short are mirror images of each other

        Keyword arguments:
        market_slug -- string "slug" (relatively short human-readable identifier)
            from /markets API call
        token_type --  value from `TokenType` enum (i.e. SHORT or LONG)
        page -- integer page number to get results from. Note that first page
            is at page=0 (default: None which means get all pages)
        per_page -- integer number of records per page (default: None and
            falls back to default value in `_request_paginated`)
        """
        if not isinstance(token_type, TokenType):
            token_type = TokenType(token_type)
        return self._request_paginated(
            method="GET",
            url="{}markets/{}/{}/order_fills".format(
                self._veil_api_url, market_slug, token_type.value),
            page=page,
            per_page=per_page
        )

    def get_my_orders(
        self,
        market_slug,
        order_status=OrderStatus.OPEN,
        page=None,
        per_page=None,
    ):
        """Get all orders associated with the user

        Keyword arguments:
        market_slug -- string "slug" (relatively short human-readable identifier)
            from /markets API call
        order_status -- value from `OrderStatus` enum (default: OrderStats.OPEN)
        page -- integer page number to get results from. Note that first page
            is at page=0 (default: None which means get all pages)
        per_page -- integer number of records per page (default: None and
            falls back to default value in `_request_paginated`)
        """
        if order_status and not isinstance(order_status, OrderStatus):
            order_status = OrderStatus(order_status)
        params = {
            "market": market_slug
        }
        if order_status is not None:
            params["status"] = order_status.value
        orders = self._request_paginated(
            method="GET",
            url="{}orders".format(self._veil_api_url),
            params=params,
            page=page,
            per_page=per_page,
            requires_session=True,
        )
        return orders

    def _request(  # pylint: disable=no-self-use
        self,
        method,
        url,
        params=None,
        requires_session=False,
        raise_on_error=True,
    ):
        """Helper function for handling get requests

        Keyword arguments:
        method -- one of {'GET', 'POST', 'DELETE'}
        url -- full path to endpoint
        params -- dictionary of parameters for endpoint (default: None)
        requires_session -- boolean of whether the request requires the session
            token to be passed in the header (default: False)
        raise_on_error -- boolean of whether should raise exception if there
            is an error (default: True)
        """
        params = params or {}
        headers = {}
        LOGGER.debug("sending %s request url=%s with params=%s",
                     method, url, params)
        if requires_session:
            headers = {
                "Authorization": "Bearer {}".format(self.session_token)}
        if method == "GET":
            res = requests.get(url, params=params, headers=headers)
        elif method == "POST":
            res = requests.post(url, json=params, headers=headers)
        else:
            raise Exception("method must be one of {'GET', 'POST'}")
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
        content_type = res.headers.get("content-type")
        if "application/json" in content_type:
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

    def _request_paginated(
        self,
        method,
        url,
        params=None,
        page=None,
        per_page=20,
        requires_session=False,
        raise_on_error=True,
    ):
        """ Helper function for handling get requests with pagination

        Keyword arguments:
        method -- one of {'GET', 'POST', 'DELETE'}
        url -- full path to endpoint
        params -- dictionary of parameters for endpoint (default: None)
        page -- integer page number to get results from. Note that first page
            is at page=0 (default: None which means get all pages)
        per_page -- integer number of records per page (default: 20 but only
            honored if a valid `page` is passed in)
        requires_session -- boolean of whether the request requires the session
            token to be passed in the header (default: False)
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
            this_res = self._request(
                method=method,
                url=url,
                params=params,
                requires_session=requires_session,
                raise_on_error=raise_on_error,
            )
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
