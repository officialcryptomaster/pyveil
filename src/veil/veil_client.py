"""
Client for interacting with veil.co API

author: officialcryptomaster@gmail.com
"""
from datetime import datetime
from enum import Enum
import logging
from decimal import Decimal
from typing import Dict, List, Optional, Tuple, Union, cast

import attr
import requests
from hexbytes import HexBytes
import jwt
import pandas as pd

from utils.logutils import setup_logger
from utils.miscutils import (
    epoch_msecs_to_local_datetime,
    epoch_secs_to_local_datetime,
    now_epoch_secs)
from utils.web3utils import (
    get_clean_address_or_throw,
    get_hexstr_or_throw,
    from_wei)
from utils.zeroexutils import ZxWeb3Client, ZxSignedOrder
from veil.constants import NETWORK_INFO


LOGGER = setup_logger(__name__, log_level=logging.INFO)

TEN_18 = 10 ** 18


def veil_price_to_eth(veil_price, num_ticks):
    """Get price in ether as a Decimal between 0 and 1.

    Args:
        veil_price (numlike): price between "0" and num_ticks
        num_ticks (int): number of ticks (from `Market.num_ticks`)
    """
    if num_ticks is None:  # for binary markets
        num_ticks = 10000.
    return Decimal(veil_price) / num_ticks


def eth_to_veil_price(eth_price, num_ticks):
    """Get price in veil as integer-like string between 0 and num_ticks.

    Args:
        eth_price (numlike): price of 1 share in ETH (i.e. between 0 and 1)
        num_ticks (int): number of ticks (from `Market.num_ticks`)
    """
    if num_ticks is None:  # for binary markets
        num_ticks = 10000.
    return "{:.0f}".format(round(Decimal(eth_price) * num_ticks))


def veil_shares_to_amount(veil_shares, num_ticks):
    """Get numeric amount of shares beween 0 and 1 from veil shares.

    Args:
        veil_shares (intlike) -- number of veil shares which is between "0"
            and amount in WEI divided by num_ticks (e.g. for binary markets,
            which have num_ticks=10000, amount of 1 is equal to 1e14
            veil_shares expressed as the integer string "100000000000000")
        num_ticks (int): number of ticks (from `Market.num_ticks`)
    """
    if num_ticks is None:  # for binary markets
        num_ticks = 10000.
    return Decimal(veil_shares) / TEN_18 * num_ticks


def amount_to_veil_shares(amount, num_ticks):
    """Get veil shares as string from amount.

    Note: veil_shares are integer string between "0" and amount in WEI
    divided by num_ticks (e.g. for binary markets, which have
    num_ticks=10000, amount of 1 is equal to 1e14 veil_shares expressed as
    the integer string "100000000000000")

    Args:
        amount (numlike): number of shares to purchase (i.e. 1 means purchase
            1 share)
        num_ticks (int): number of ticks (from `Market.num_ticks`)
    """
    if num_ticks is None:  # for binary markets
        num_ticks = 10000.
    return "{:.0f}".format(round(Decimal(amount) * TEN_18 / num_ticks))


def dict_to_zx_order(signed_order_dict) -> ZxSignedOrder:
    """Get a ZxSignedOrder from a dict."""
    return ZxSignedOrder(**signed_order_dict)


def get_veil_zx_order_from_signed_order(signed_order):
    """Get a Veil-compatible json 0x signed order from a `ZxSignedOrder` instance"""
    return {
        "maker_address": signed_order.maker_address_,
        "taker_address": signed_order.taker_address_,
        "fee_recipient_address": signed_order.fee_recipient_address_,
        "sender_address": signed_order.sender_address_,
        "exchange_address": signed_order.exchange_address_,
        "maker_asset_amount": signed_order.maker_asset_amount_,
        "taker_asset_amount": signed_order.taker_asset_amount_,
        "maker_fee": signed_order.maker_fee_,
        "taker_fee": signed_order.taker_fee_,
        "salt": signed_order.salt_,
        "expiration_time_seconds": str(signed_order.expiration_time_seconds_),
        "maker_asset_data": signed_order.maker_asset_data_,
        "taker_asset_data": signed_order.taker_asset_data_,
        "signature": signed_order.signature,
    }


class MarketStatus(Enum):
    """Market status value strings."""
    OPEN = "open"
    RESOLVED = "resolved"


class MarketType(Enum):
    """Market type value strings."""
    SCALAR = "scalar"
    YESNO = "yesno"


class TokenType(Enum):
    """Token type strings."""
    LONG = "long"
    SHORT = "short"


class OrderSide(Enum):
    """Order side value strings."""
    BUY = "buy"
    SELL = "sell"


class OrderPriceType(Enum):
    """Order price type value string."""
    LIMIT = "limit"


class OrderStatus(Enum):
    """Order status value strings."""
    OPEN = "open"
    FILLEd = "filled"
    CANCELED = "canceled"
    EXPIRED = "expired"
    PENDING = "pending"
    COMPLETED = "completed"


@attr.s(kw_only=True, slots=True)
class BookEntry:
    """An entry (bid or ask) in an Orderbook."""
    price: int = attr.ib(converter=int)
    token_amount: int = attr.ib(converter=int)


def list_to_book_entries(list_of_dicts) -> List[BookEntry]:
    """Get a list of `BookEntry` objects from list of dicts."""
    return [BookEntry(**entry) for entry in list_of_dicts]


@attr.s(kw_only=True, slots=True)
class SideBook:
    """Get a `SideBook` (can be bid-side or ask-side)."""
    side: OrderSide = attr.ib(converter=OrderSide)
    entries: List[BookEntry] = attr.ib(converter=list_to_book_entries)


@attr.s(kw_only=True, slots=True)
class OrderFill:
    """Order fill object."""
    uid: str = attr.ib()
    status: OrderStatus = attr.ib(converter=OrderStatus)
    token_amount: int = attr.ib(converter=int)
    created_at: datetime = attr.ib(converter=epoch_msecs_to_local_datetime)
    price: Optional[int] = attr.ib(
        default=None, converter=attr.converters.optional(int))
    side: Optional[OrderSide] = attr.ib(
        default=None, converter=attr.converters.optional(OrderSide))


def optional_dict_to_order_fill(order_dict) -> Optional[OrderFill]:
    """Get a list of `OrderFill` objects from list of dicts."""
    if order_dict is None:
        return None
    return OrderFill(**order_dict)


def list_of_dicts_to_list_of_fills(list_of_fills) -> List[OrderFill]:
    """Convert list of dicts to list of `OrderFill` objects."""
    return [OrderFill(**fill) for fill in list_of_fills]


@attr.s(kw_only=True, slots=True)
class Order:
    """Order object."""
    uid: str = attr.ib()
    status: OrderStatus = attr.ib(converter=OrderStatus)
    created_at: datetime = attr.ib(converter=epoch_msecs_to_local_datetime)
    expires_at: datetime = attr.ib(converter=epoch_msecs_to_local_datetime)
    type: OrderPriceType = attr.ib(converter=OrderPriceType)
    token_type: TokenType = attr.ib(converter=TokenType)
    side: OrderSide = attr.ib(converter=OrderSide)
    price: int = attr.ib(converter=int)
    token: str = attr.ib(converter=get_clean_address_or_throw)
    token_amount: int = attr.ib(converter=int)
    token_amount_clean: Optional[str] = attr.ib(default=None)
    token_amount_filled: int = attr.ib(converter=int)
    currency: str = attr.ib(converter=get_clean_address_or_throw)
    currency_amount: int = attr.ib(converter=int)
    currency_amount_clean: Optional[str] = attr.ib(default=None)
    currency_amount_filled: int = attr.ib(converter=int)
    post_only: bool = attr.ib(converter=bool)
    market: Optional[Dict] = attr.ib(factory=dict)
    fills: List[OrderFill] = attr.ib(
        converter=list_of_dicts_to_list_of_fills)
    zero_ex_order: Optional[ZxSignedOrder] = attr.ib(
        default=None,
        converter=attr.converters.optional(dict_to_zx_order))


def optional_dict_to_order(order_dict) -> Optional[Order]:
    """Convert a dict to Order object if not None."""
    if order_dict is None:
        return None
    return Order(**order_dict)


def list_of_dicts_to_orders(list_of_fills) -> List[Order]:
    """Convert list of dicts to list of `Order` objects."""
    return [Order(**fill) for fill in list_of_fills]


@attr.s(kw_only=True, slots=True)
class Market:
    """Market information object."""
    uid: str = attr.ib()
    slug: str = attr.ib()
    name: str = attr.ib(validator=attr.validators.instance_of(str))
    address: str = attr.ib(converter=get_clean_address_or_throw)
    created_at: datetime = attr.ib(converter=epoch_msecs_to_local_datetime)
    ends_at: datetime = attr.ib(converter=epoch_msecs_to_local_datetime)
    details: str = attr.ib(validator=attr.validators.instance_of(str))
    num_ticks: int = attr.ib(converter=int)
    min_price: Optional[int] = attr.ib(
        default=None, converter=attr.converters.optional(int))
    max_price: Optional[int] = attr.ib(
        default=None, converter=attr.converters.optional(int))
    limit_price: Optional[int] = attr.ib(
        default=None, converter=attr.converters.optional(int))
    type: MarketType = attr.ib(converter=MarketType)
    result: str = attr.ib()
    long_buyback_order: Optional[Order] = attr.ib(
        default=None, converter=attr.converters.optional(optional_dict_to_order))
    short_buyback_order: Optional[Order] = attr.ib(
        default=None, converter=attr.converters.optional(optional_dict_to_order))
    long_token: str = attr.ib(converter=get_clean_address_or_throw)
    short_token: str = attr.ib(converter=get_clean_address_or_throw)
    denomination: str = attr.ib()
    channel: str = attr.ib()
    index: str = attr.ib()
    predicted_price: Optional[int] = attr.ib(
        default=None, converter=attr.converters.optional(int))
    last_trade_price: Optional[int] = attr.ib(
        default=None, converter=attr.converters.optional(int))
    metadata: Dict = attr.ib(validator=attr.validators.instance_of(dict))
    final_value: Optional[str] = attr.ib(default=None)
    is_deleted: bool = attr.ib(converter=bool)
    is_delisted: bool = attr.ib(converter=bool)
    is_trading_paused: bool = attr.ib(converter=bool)
    is_draft: bool = attr.ib(converter=bool)
    review_status: str = attr.ib(converter=str)
    status: str = attr.ib(converter=str)
    trade_fee: str = attr.ib()


def optional_dict_to_market(market_dict) -> Optional[Market]:
    """Convert a dict to Market object if not None."""
    if market_dict is None:
        return None
    return Market(**market_dict)


@attr.s(kw_only=True, slots=True)
class QuoteResponse:
    """Quote response object required for making an order."""
    uid: str = attr.ib()
    side: OrderSide = attr.ib(converter=OrderSide)
    type: OrderPriceType = attr.ib(converter=OrderPriceType)
    price: int = attr.ib(converter=int)
    token_amount: int = attr.ib(converter=int)
    currency_amount: int = attr.ib(converter=int)
    order_hash: str = attr.ib(converter=get_hexstr_or_throw)
    created_at: datetime = attr.ib(converter=epoch_msecs_to_local_datetime)
    expires_at: datetime = attr.ib(converter=epoch_msecs_to_local_datetime)
    quote_expires_at: datetime = attr.ib(converter=epoch_msecs_to_local_datetime)
    token: str = attr.ib(converter=get_clean_address_or_throw)
    currency: str = attr.ib(converter=get_clean_address_or_throw)
    fillable_token_amount: int = attr.ib(converter=int)
    fee_amount: int = attr.ib(converter=int)
    fee_breakdown: Optional[dict] = attr.ib(default=None)
    zero_ex_order: ZxSignedOrder = attr.ib(converter=dict_to_zx_order)


@attr.s(kw_only=True, slots=True)
class MarketBalances:
    """Market balances of a given user."""
    slug: str = attr.ib()
    long_balance: int = attr.ib(converter=int)
    short_balance: int = attr.ib(converter=int)
    long_balance_clean: int = attr.ib(converter=int)
    short_balance_clean: int = attr.ib(converter=int)
    veil_ether_balance: int = attr.ib(converter=int)
    ether_balance: int = attr.ib(converter=int)

    def __attrs_post_init__(self):
        self.long_balance_clean = from_wei(self.long_balance_clean)
        self.short_balance_clean = from_wei(self.short_balance_clean)
        self.veil_ether_balance = from_wei(self.veil_ether_balance)
        self.ether_balance = from_wei(self.ether_balance)


def entries_to_dataframe(entries) -> pd.DataFrame:
    """Turn data feed entries into a pandas dataframe for use of use."""
    dataframe = pd.DataFrame(entries)
    dataframe["timestamp"] = pd.to_datetime(dataframe["timestamp"], unit="ms")
    return dataframe.set_index("timestamp")


@attr.s(kw_only=True, slots=True)
class DataFeed:
    """Data feed object."""
    uid: str = attr.ib()
    name: str = attr.ib()
    description: str = attr.ib()
    denomination: str = attr.ib()
    entries: pd.DataFrame = attr.ib(converter=entries_to_dataframe, repr=False)


class VeilClient(ZxWeb3Client):
    """Client for interacting with veil.co API."""

    __name__ = "VeilClient"

    VEIL_DECIMALS = 14

    def __init__(
        self,
        network_id: int,
        web3_rpc_url: str,
        private_key: Union[HexBytes, str] = None,
        min_amount: Decimal = Decimal("0.005"),
        max_amount: Decimal = Decimal(1),
    ):
        """Create an instance of VegaRelayClient.

        Args:
            network_id (int): id of network from :class:`NetworkId`
            web3_rpc_url (str): URL of the Web3 service
            private_key (:class:`HexBytes` or strstr): hex bytes or hexstr
                of private key for signing transactions (must be convertible
                to :class:`HexBytes`) (default: None)
            min_amount (int): minimum amount of shares allowable in single
                transaction
            max_amount (int): maximum amount of shares allowable in single
                transaction
        """
        super(VeilClient, self).__init__(
            network_id=network_id,
            web3_rpc_url=web3_rpc_url,
            private_key=private_key,
        )
        self._veil_api_url = NETWORK_INFO[self.network_id]["veil_api_url"]
        self._min_amount: Decimal = Decimal(min_amount)
        self._max_amount: Decimal = Decimal(max_amount)
        self._session_challenge: Optional[Dict] = None
        self._session_info: Optional[Dict] = None
        # cache markets by filter tuple (we will never cache raw results)
        self._markets: Dict[
            Union[Tuple, str],
            Union[Market, List[Market]]] = {}

    def _str_arg_append(self):
        """String to append to list of params for `__str__`"""
        return (
            f", authenticated={self._session_info is not None}"
            f", min_amount={self._min_amount}"
            f", max_amount={self._max_amount}"
        )

    @property
    def session_info(self):
        """Get the session information.

        Will force authentication if self._session_info is missing or
        is withing 30 seconds of expiry.
        """
        need_auth = self._session_info is None
        if self._session_info:
            now = now_epoch_secs()
            exp = self._session_info["exp"]
            need_auth = (exp - now) < 30
        if need_auth:
            self._authenticate(force=True)
        return self._session_info

    @property
    def session_token(self) -> str:
        """Get the session token (forces authentication if missing)."""
        return self.session_info["token"]

    @property
    def session_expiry(self) -> datetime:
        """Get session expiry in seconds after epoch."""
        return epoch_secs_to_local_datetime(self.session_info["exp"])

    @property
    def veil_account(self):
        """Get the VegaRelay session account (forces authentication if missing)."""
        return self.session_info["account"]

    def _authenticate(self, force: bool = False):
        """Get a session challenge, sign it, and get valid session token.

        Args:
            force (bool): get and sign a new token regardless of whether we
                already have a valid session token.
        """
        if not force and self._session_info:
            return self
        challenge = self.get_session_challenge()["uid"]
        signed_challenge = self.sign_hash(
            HexBytes(challenge.encode("utf-8"))
        )["signature"].hex()
        self._session_info = self._request(
            method="POST",
            url="{}sessions".format(self._veil_api_url),
            params={
                "challengeUid": challenge,
                "message": challenge,
                "signature": signed_challenge,
            },
        )["data"]
        if self._session_info:
            token_info = jwt.decode(self._session_info["token"], verify=False)
            self._session_info.update(token_info)
            self._session_info["challenge"] = challenge
        return self

    def get_session_challenge(self):
        """Get a session challenge for authentication."""
        session_challenge = self._request(
            method="POST",
            url="{}session_challenges".format(self._veil_api_url)
        )
        self._session_challenge = session_challenge["data"]
        return self._session_challenge

    def get_markets(
        self,
        channel: str = None,
        status: Optional[MarketStatus] = None,
        page: Optional[int] = None,
        per_page: Optional[int] = None,
        force_refresh: bool = False,
        raw_json: bool = False,
    ) -> Union[List[Market], List[Dict]]:
        """Fetch list of markets optionally filterd on channel or status
        Note: Public endpoint, does not need an account

        Args:
            channel (str): channel for filtering
                (default: None which means no filtering based on channel)
            status (:class:`MarketStatus`): enum for filtering
                (default: None which means no filtering based on status)
            page (int): page number to get results from. Note that first page
                is at page=0 (default: None which means get all pages)
            per_page (int): number of records per page (default: None and
                falls back to default value in `_request_paginated`)
            force_refresh (bool): whether results should be fetched again
                from server or from in-memory cache (default: False)
            raw_json (bool): whether the result should be left as a raw json or
                converted to a list of :class:`Market` objects (default: False)

        Returns:
            (List[:class:`Market`]) list of markets.
        """
        if not raw_json and not force_refresh and self._markets is not None:
            markets = self._markets.get((channel, status, page, per_page))
            if markets is not None:
                return cast(List[Market], markets)
        params = {}
        if channel:
            params["channel"] = channel
        if status:
            if not isinstance(status, MarketStatus):
                status = MarketStatus(status)
            params["status"] = status.value
        res = self._request_paginated(
            method="GET",
            url="{}markets".format(self._veil_api_url),
            params=params,
            page=page,
            per_page=per_page,
            raw_json=raw_json,
        )
        if raw_json:
            return res
        markets = [Market(**m) for m in res]
        self._markets[(channel, status, page, per_page)] = markets
        return markets

    def get_market(
        self,
        market_slug: str,
        force_refresh: bool = False,
        raw_json: bool = False,
    ) -> Union[Market, Dict]:
        """Fetch a single market using the market "slug" identifier.
        Note: Public endpoint, does not need an account

        Args:
            market_slug (str): "slug" (relatively short human-readable
                identifier) from /markets API cal
            force_refresh (bool): whether results should be fetched again
                from server or from in-memory cache (default: False)
            raw_json (bool): whether the result should be left as a raw json or
                converted to a :class:`Market` object (default: False)

        Returns:
            (:class:`Market`) market.
        """
        if not raw_json and not force_refresh and self._markets is not None:
            market = self._markets.get(market_slug)
            if market is not None:
                return cast(Market, market)
        res = self._request(
            method="GET",
            url="{}markets/{}".format(self._veil_api_url, market_slug),
        )
        if raw_json:
            return res
        market = Market(**res["data"])
        self._markets[market_slug] = market
        return market

    def get_feed_data(
        self,
        feed_name: str,
        scope: str = "month",
        raw_json: bool = False,
    ) -> Union[DataFeed, Dict]:
        """Fetch feed data using `Market.index`.

        Args:
            feed_name (str): name of feed from `Market.index`
            raw_json (bool): whether the result should be left as a raw json
                or converted to a :class:`DataFeed` object (default: False)

        Returns:
            (:class:`DataFeed`) data feed.
        """
        res = self._request(
            method="GET",
            url="{}data_feeds/{}".format(self._veil_api_url, feed_name),
            params={"scope": scope},
        )
        if raw_json:
            return res
        data_feed = DataFeed(**res["data"])
        return data_feed

    def get_bids(
        self,
        market_slug: str,
        token_type: TokenType,
        page: Optional[int] = None,
        per_page: Optional[int] = None,
        raw_json: bool = False,
    ) -> Union[SideBook, Dict]:
        """Fetch the long/short bids for a given market.

        Note that long and short are mirror images of each other

        Args:
            market_slug (str): "slug" (relatively short human-readable
                identifier) from /markets API cal
            token_type (:class:`TokenType`): enum for filtering
            page (int): page number to get results from. Note that first page
                is at page=0 (default: None which means get all pages)
            per_page (int): number of records per page (default: None and
                falls back to default value in `_request_paginated`)
            force_refresh (bool): whether results should be fetched again
                from server or from in-memory cache (default: False)
            raw_json (bool): whether the result should be left as a raw json or
                converted to a :class:`SideBook` object (default: False)

        Returns:
            (:class:`SideBook`) of bids.
        """
        if not isinstance(token_type, TokenType):
            token_type = TokenType(token_type)
        res = self._request_paginated(
            method="GET",
            url="{}markets/{}/{}/bids".format(
                self._veil_api_url, market_slug, token_type.value),
            page=page,
            per_page=per_page,
            raw_json=raw_json,
        )
        if raw_json:
            return res
        sidebook = SideBook(side=OrderSide.BUY, entries=res)
        return sidebook

    def get_asks(
        self,
        market_slug: str,
        token_type: TokenType,
        page: Optional[int] = None,
        per_page: Optional[int] = None,
        raw_json: bool = False,
    ) -> Union[SideBook, Dict]:
        """Fetch the long/short asks for a given market.

        Note that long and short are mirror images of each other

        Args:
            market_slug (str): "slug" (relatively short human-readable
                identifier) from /markets API cal
            token_type (:class:`TokenType`): enum for filtering
            page (int): page number to get results from. Note that first page
                is at page=0 (default: None which means get all pages)
            per_page (int): number of records per page (default: None and
                falls back to default value in `_request_paginated`)
            force_refresh (bool): whether results should be fetched again
                from server or from in-memory cache (default: False)
            raw_json (bool): whether the result should be left as a raw json or
                converted to a :class:`SideBook` object (default: False)

        Returns:
            (:class:`SideBook`) of asks.
        """
        if not isinstance(token_type, TokenType):
            token_type = TokenType(token_type)
        res = self._request_paginated(
            method="GET",
            url="{}markets/{}/{}/asks".format(
                self._veil_api_url, market_slug, token_type.value),
            page=page,
            per_page=per_page,
            raw_json=raw_json
        )
        if raw_json:
            return res
        sidebook = SideBook(side=OrderSide.SELL, entries=res)
        return sidebook

    def get_order_fills(
        self,
        market_slug: str,
        token_type: TokenType,
        page: Optional[int] = None,
        per_page: Optional[int] = None,
        raw_json: bool = False,
    ) -> Union[List[OrderFill], List[Dict]]:
        """Fetch the order fill history for a given long or short market.

        Note that long and short are mirror images of each other

        Args:
            market_slug (str): "slug" (relatively short human-readable
                identifier) from /markets API cal
            token_type (:class:`TokenType`): enum for filtering
            page (int): page number to get results from. Note that first page
                is at page=0 (default: None which means get all pages)
            per_page (int): number of records per page (default: None and
                falls back to default value in `_request_paginated`)
            force_refresh (bool): whether results should be fetched again
                from server or from in-memory cache (default: False)
            raw_json (bool): whether the result should be left as a raw json or
                converted to a list of :class:`OrderFill` objects (default: False)

        Returns:
            (List[:class:`OrderFill`]) list of order fills.
        """
        if not isinstance(token_type, TokenType):
            token_type = TokenType(token_type)
        res = self._request_paginated(
            method="GET",
            url="{}markets/{}/{}/order_fills".format(
                self._veil_api_url, market_slug, token_type.value),
            page=page,
            per_page=per_page,
            raw_json=raw_json,
        )
        if raw_json:
            return res
        order_fills = [OrderFill(**order_fill) for order_fill in res]
        return order_fills

    def post_order(
        self,
        market: Market,
        token_type: TokenType,
        side: OrderSide,
        amount: Decimal,
        price: Decimal,
        order_price_type: OrderPriceType = OrderPriceType.LIMIT,
        raw_json: bool = False,
    ) -> Union[Order, Dict]:
        """Get a Veil quote, sign the order on it and post the order

        Args:
            market (:class:`Market`): market to post order for.
            token_type (:class:`TokenType`): enum for filtering
            side (:class:`OrderSide` or str): order side
            amount (Decimal): token amount (1 means 1 share)
            price (Decimal): numeric-like price in ETH (i.e. between 0 and 1)
            order_price_type (:class:`OrderPriceType`): (default: `OrderPriceType.LIMIT`)
            raw_json (bool): whether the result should be left as a raw json or
                converted to a :class:`QuoteResponse` object (default: False)

        Returns:
            (:class:`Order`) posted order.
        """
        res = self._get_quote(
            market=market,
            token_type=token_type,
            side=side,
            amount=amount,
            price=price,
            order_price_type=order_price_type,
        )
        quote = cast(QuoteResponse, res)
        zx_order = quote.zero_ex_order
        zx_order.signature = self.sign_hash_zx_compat(zx_order.hash)
        order_res = self._post_order(
            quote_id=quote.uid,
            signed_order=zx_order,
            raw_json=raw_json,
        )
        return order_res

    def _post_order(
        self,
        quote_id: str,
        signed_order: ZxSignedOrder,
        raw_json: bool = False,
    ) -> Union[Order, Dict]:
        """Post a signed order.

        Args:
            quote_id (str): id of the quote acquired from :method:`get_quote`.
            signed_order (:class:`ZxSignedOrder`): signed 0x order.
            raw_json (bool): whether the result should be left as a raw json
                or converted to a :class:`Order` object (default: False).

        Returns:
            (:class:`Order`) posted order.
        """
        params = {
            "order": {
                "quote_uid": quote_id,
                "zero_ex_order": get_veil_zx_order_from_signed_order(signed_order)
            }
        }
        res = self._request(
            method="POST",
            url="{}orders".format(self._veil_api_url),
            params=params,
            requires_session=True,
        )
        if raw_json:
            return res
        order = Order(**res["data"])
        order.zero_ex_order = signed_order
        return order

    def _get_quote(
        self,
        market: Market,
        token_type: TokenType,
        side: OrderSide,
        amount: Decimal,
        price: Decimal,
        order_price_type: OrderPriceType = OrderPriceType.LIMIT,
        raw_json: bool = False,
    ) -> Union[QuoteResponse, Dict]:
        """Get the template for 0x order to sign.

        Args:
            market (:class:`Market`): market instance
            token_type (:class:`TokenType`): enum for filtering
            side :class:`OrderSide`: order side (i.e. "long", "short")
            amount (Decimal): token amount (1 means 1 share)
            price (Decimal): numeric-like price in ETH (i.e. between 0 and 1)
            order_price_type (:class:`OrderPriceType`): enum value
                (default: `OrderPriceType.LIMIT`)
            raw_json (bool): whether the result should be left as a raw json
                or converted to a :class:`QuoteResponse` object. (default:
                False)

        Returns:
            (:class:`QuoteResponse`) quote response.
        """
        if not isinstance(side, OrderSide):
            side = OrderSide(side)
        if not isinstance(token_type, TokenType):
            token_type = TokenType(token_type)
        if token_type == TokenType.LONG:
            token_address = market.long_token
        elif token_type == TokenType.SHORT:
            token_address = market.short_token
        else:
            raise Exception("token_type must be valid type from `TokenType` enum")
        amount = Decimal(amount)
        if amount < self._min_amount or amount > self._max_amount:
            raise TypeError(
                ("quote amount outside acceptable range: amount='{}',"
                 " but expected '{}' < amount < '{}'").format(
                    amount, self._min_amount, self._max_amount))
        price = Decimal(price)
        if price < 0 or price > 1.0:
            raise Exception(
                ("quote price outisde acceptable range: got: price='{}',"
                 " but expected {} < price < {}").format(
                     price, market.min_price, market.max_price))
        if not isinstance(order_price_type, OrderPriceType):
            order_price_type = OrderPriceType(order_price_type)
        params = {
            "quote": {
                "side": side.value,
                "token": token_address,
                "token_amount": amount_to_veil_shares(amount, market.num_ticks),
                "price": eth_to_veil_price(price, market.num_ticks),
                "type": order_price_type.value,
            }
        }
        res = self._request(
            method="POST",
            url="{}quotes".format(self._veil_api_url),
            params=params,
            requires_session=True,
        )
        if raw_json:
            return res
        quote_response = QuoteResponse(**res["data"])
        return quote_response

    def get_orders(
        self,
        market_slug: str,
        order_status: OrderStatus = OrderStatus.OPEN,
        page: Optional[int] = None,
        per_page: Optional[int] = None,
        raw_json: bool = False,
    ) -> Union[List[Order], List[Dict]]:
        """Fetch orders associated with the user for a given market.

        Args:
            market_slug (str): relatively short human-readable
                identifier from /markets API call
            order_status (:class:`OrderStatus` or str): enum
                (default: OrderStats.OPEN)
            page (int): page number to get results from. Note that first page
                is at page=0 (default: None which means get all pages)
            per_page (int): number of records per page (default: None and
                falls back to default value in `_request_paginated`)
            raw_json (bool): whether the result should be left as a raw json
                or converted to a list of :class:`Order` objects (default:
                False)

        Returns:
            (List[:class:`Order`]) list of orders.
        """
        if order_status and not isinstance(order_status, OrderStatus):
            order_status = OrderStatus(order_status)
        params = {
            "market": market_slug
        }
        if order_status is not None:
            params["status"] = order_status.value
        res = self._request_paginated(
            method="GET",
            url="{}orders".format(self._veil_api_url),
            params=params,
            page=page,
            per_page=per_page,
            requires_session=True,
            raw_json=raw_json,
        )
        if raw_json:
            return res
        orders = [Order(**order) for order in res]
        return orders

    def cancel_order(
        self,
        order_id: str,
        raw_json: bool = False,
    ) -> Union[Order, Dict]:
        """Cancel an order using its uid.

        Args:
            order_id (str): `uid` from `QuoteResponse` or `Order`
            raw_json (bool) -- whether the result should be left as a raw json or
                converted to a :class:`Order` object (default: False)

        Returns:
            (:class:`Order`) cancelled order.
        """
        res = res = self._request(
            method="DELETE",
            url="{}orders/{}".format(self._veil_api_url, order_id),
            requires_session=True,
        )
        if raw_json:
            return res
        order = Order(**res["data"])
        return order

    def get_balances(
        self,
        market_slug: str,
        raw_json: bool = False,
    ):
        """Fetch position balances associated with the user for a given market

        Args:
            market_slug (str): relatively short human-readable
                identifier from /markets API call
            raw_json (bool): whether the result should be left as a raw json
                or converted to a :class:`MarketBalances` object
                (default: False)

        Returns:
            (:class:`MarketBalances`) market balances.
        """
        res = self._request(
            method="GET",
            url="{}markets/{}/balances".format(self._veil_api_url, market_slug),
            requires_session=True,
        )
        if raw_json:
            return res
        balances = res["data"]
        balances["slug"] = market_slug
        balances = MarketBalances(**balances)
        return balances

    def _request(  # pylint: disable=no-self-use
        self,
        method: str,
        url: str,
        params: Optional[Dict] = None,
        requires_session: bool = False,
        raise_on_error: bool = True,
    ):
        """Helper function for handling get requests.

        Args:
            method (str): request method (one of {'GET', 'POST', 'DELETE'})
            url (str): full path to endpoint
            params (dict): parameters for endpoint (default: None)
            requires_session (bool): whether the request requires the session
                token to be passed in the header (default: False)
            raise_on_error (bool): whether should raise exception if there
                is an error (default: True)
        """
        params = params or {}
        headers: Dict = {}
        LOGGER.debug("sending %s request url=%s with params=%s",
                     method, url, params)
        if requires_session:
            headers = {
                "Authorization": "Bearer {}".format(self.session_token)}
        if method == "GET":
            res = requests.get(url, params=params, headers=headers)
        elif method == "POST":
            res = requests.post(url, json=params, headers=headers)
        elif method == "DELETE":
            res = requests.delete(url, headers=headers)
        else:
            raise Exception("method must be one of {'GET', 'POST', 'DELETE'}")

        ret_val = None
        # LOGGER.debug("HEADERS: %s", res.headers)
        LOGGER.debug("CONTENT: %s", res.content)
        content_type: str = res.headers.get("content-type", "")
        if "application/json" in content_type:
            try:
                ret_val = res.json()
            except Exception as ex:  # pylint: disable=broad-except
                LOGGER.exception(
                    "result with status_code=%s was not a"
                    " valid json", res.status_code
                )
                if raise_on_error:
                    raise ex
        else:
            ret_val = res.content

        if res.status_code != 200:
            err_msg = (
                f"request failed with status_code={res.status_code}."
                f" content={ret_val}")
            LOGGER.error(err_msg)
            if raise_on_error:
                raise Exception(err_msg)
        return ret_val

    def _request_paginated(
        self,
        method: str,
        url: str,
        params: Optional[Dict] = None,
        page: Optional[int] = None,
        per_page: Optional[int] = None,
        requires_session: bool = False,
        raise_on_error: bool = True,
        raw_json: bool = False,
    ):
        """ Helper function for handling get requests with pagination.

        Args:
            method (str): request method (one of {'GET', 'POST', 'DELETE'})
            url (str): full path to endpoint
            params (dict): parameters for endpoint (default: None)
            page (int): page number to get results from. Note that first page
                is at page=0 (default: None which means get all pages)
            per_page (int): number of records per page (default: 20 but only
                honored if a valid `page` is passed in)
            requires_session (bool): whether the request requires the session
                token to be passed in the header (default: False)
            raise_on_error (bool): whether should raise exception if there
                is an error (default: True)
            raw_json (bool): whether the result should be left as a list of
                raw json objects or converted to single list of results.
        """
        params = params or {}
        res = []
        if page is not None and page > -1:
            next_page = page
        else:
            next_page = 0  # pages start at 0
        while True:
            params["page"] = next_page
            params["per_page"] = per_page if per_page is not None else 20
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
            if not this_data["results"]:
                break
            if raw_json:
                res.append(this_data)
            else:
                res.extend(this_data["results"])
                tot_recs = int(this_data["total"])
                if page is not None or len(res) == tot_recs:
                    break
            next_page = next_page + 1
        return res
