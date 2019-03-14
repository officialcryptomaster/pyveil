"""
Client for interacting with veil.co API

author: officialcryptomaster@gmail.com
"""
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict
from decimal import Decimal
import logging
import requests
import attr
from hexbytes import HexBytes
import pandas as pd
from veil.constants import NETWORK_INFO
from utils.logutils import setup_logger
from utils.miscutils import epoch_msecs_to_local_datetime
from utils.web3utils import get_clean_address_or_throw, get_hexstr_or_throw, from_base_unit_amount
from utils.zeroexutils import ZxWeb3Client, ZxSignedOrder


LOGGER = setup_logger(__name__, log_level=logging.INFO)

TEN_18 = 10 ** 18


def veil_price_to_eth(veil_price, num_ticks):
    """Get price in ether as a Decimal between 0 and 1

    Keyword arguments:
    veil_price -- price between "0" and num_ticks
    num_ticks -- integer number of ticks (from `Market.num_ticks`)
    """
    if num_ticks is None:  # for binary markets
        num_ticks = 10000.
    return Decimal(veil_price) / num_ticks


def eth_to_veil_price(eth_price, num_ticks):
    """Get price in veil as integer-like string between 0 and num_ticks

    Keyword arguments:
    eth_price -- numeric price of 1 share in ETH (i.e. between 0 and 1)
    num_ticks -- integer number of ticks (from `Market.num_ticks`)
    """
    if num_ticks is None:  # for binary markets
        num_ticks = 10000.
    return "{:.0f}".format(round(Decimal(eth_price) * num_ticks))


def veil_shares_to_amount(veil_shares, num_ticks):
    """Get numeric amount of shares beween 0 and 1 from veil shares

    Keyword arguments:
    veil_shares -- integer-like number of veil shares which is between "0"
        and amount in WEI divided by num_ticks (e.g. for binary markets,
        which have num_ticks=10000, amount of 1 is equal to 1e14 veil_shares
        expressed as the integer string "100000000000000")
    num_ticks -- integer number of ticks (from `Market.num_ticks`)
    """
    if num_ticks is None:  # for binary markets
        num_ticks = 10000.
    return Decimal(veil_shares) / TEN_18 * num_ticks


def amount_to_veil_shares(amount, num_ticks):
    """Get veil shares as string from amount

    Note: veil_shares are integer string between "0" and amount in WEI divided by
    num_ticks (e.g. for binary markets, which have num_ticks=10000, amount of 1
    is equal to 1e14 veil_shares expressed as the integer string "100000000000000")

    Keyword arguments:
    amount -- numeric number of shares to purchase (i.e. 1 means purchase 1 share)
    num_ticks -- integer number of ticks (from `Market.num_ticks`)
    """
    if num_ticks is None:  # for binary markets
        num_ticks = 10000.
    return "{:.0f}".format(round(Decimal(amount) * TEN_18 / num_ticks))


def dict_to_zx_order(signed_order_dict) -> ZxSignedOrder:
    """Get a ZxSignedOrder from a dict"""
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
    """Market status value strings"""
    OPEN = "open"
    RESOLVED = "resolved"


class MarketType(Enum):
    """Market type value strings"""
    SCALAR = "scalar"
    YESNO = "yesno"


class TokenType(Enum):
    """Token type strings"""
    LONG = "long"
    SHORT = "short"


class OrderSide(Enum):
    """Order side value strings"""
    BUY = "buy"
    SELL = "sell"


class OrderPriceType(Enum):
    """Order price type value string"""
    LIMIT = "limit"


class OrderStatus(Enum):
    """Order status value strings"""
    OPEN = "open"
    FILLEd = "filled"
    CANCELED = "canceled"
    EXPIRED = "expired"
    PENDING = "pending"
    COMPLETED = "completed"


@attr.s(kw_only=True, slots=True)
class BookEntry:
    """An entry (bid or ask) in an Orderbook"""
    price: int = attr.ib(converter=int)
    token_amount: int = attr.ib(converter=int)


def list_to_book_entries(list_of_dicts) -> List[BookEntry]:
    """Get a list of `BookEntry` objects from list of dicts"""
    return [BookEntry(**entry) for entry in list_of_dicts]


@attr.s(kw_only=True, slots=True)
class SideBook:
    """Get a `SideBook` (can be bid-side or ask-side)"""
    side: OrderSide = attr.ib(converter=OrderSide)
    entries: List[BookEntry] = attr.ib(converter=list_to_book_entries)


@attr.s(kw_only=True, slots=True)
class OrderFill:
    """Order fill object"""
    uid: str = attr.ib()
    status: OrderStatus = attr.ib(converter=OrderStatus)
    token_amount: int = attr.ib(converter=int)
    created_at: datetime = attr.ib(converter=epoch_msecs_to_local_datetime)
    price: Optional[int] = attr.ib(
        default=None, converter=attr.converters.optional(int))
    side: Optional[OrderSide] = attr.ib(
        default=None, converter=attr.converters.optional(OrderSide))


def optional_dict_to_order_fill(order_dict) -> Optional[OrderFill]:
    """Get a list of `OrderFill` objects from list of dicts"""
    if order_dict is None:
        return None
    return OrderFill(**order_dict)


def list_of_dicts_to_list_of_fills(list_of_fills) -> List[OrderFill]:
    """Convert list of dicts to list of `OrderFill` objects"""
    return [OrderFill(**fill) for fill in list_of_fills]


@attr.s(kw_only=True, slots=True)
class Order:
    """Order object"""
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
    """Convert a dict to Order object if not None"""
    if order_dict is None:
        return None
    return Order(**order_dict)


def list_of_dicts_to_orders(list_of_fills) -> List[Order]:
    """Convert list of dicts to list of `Order` objects"""
    return [Order(**fill) for fill in list_of_fills]


@attr.s(kw_only=True, slots=True)
class Market:
    """Market information object"""
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
    """Convert a dict to Market object if not None"""
    if market_dict is None:
        return None
    return Market(**market_dict)


@attr.s(kw_only=True, slots=True)
class QuoteResponse:
    """Quote response object required for making an order"""
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
    """Market balances of a given user"""
    slug: str = attr.ib()
    long_balance: int = attr.ib(converter=int)
    short_balance: int = attr.ib(converter=int)
    long_balance_clean: int = attr.ib(converter=int)
    short_balance_clean: int = attr.ib(converter=int)
    veil_ether_balance: int = attr.ib(converter=int)
    ether_balance: int = attr.ib(converter=int)

    def __attrs_post_init__(self):
        self.long_balance_clean = from_base_unit_amount(self.long_balance_clean)
        self.short_balance_clean = from_base_unit_amount(self.short_balance_clean)
        self.veil_ether_balance = from_base_unit_amount(self.veil_ether_balance)
        self.ether_balance = from_base_unit_amount(self.ether_balance)


def entries_to_dataframe(entries) -> pd.DataFrame:
    """Turn data feed entries into a pandas dataframe for use of use"""
    dataframe = pd.DataFrame(entries)
    dataframe["timestamp"] = pd.to_datetime(dataframe["timestamp"], unit="ms")
    return dataframe.set_index("timestamp")


@attr.s(kw_only=True, slots=True)
class DataFeed:
    """Data feed object"""
    uid: str = attr.ib()
    name: str = attr.ib()
    description: str = attr.ib()
    denomination: str = attr.ib()
    entries: pd.DataFrame = attr.ib(converter=entries_to_dataframe, repr=False)


class VeilClient(ZxWeb3Client):
    """Client for interacting with veil.co API"""

    __name__ = "VeilClient"

    VEIL_DECIMALS = 14

    def __init__(
        self,
        network_id,
        web3_rpc_url,
        private_key=None,
        min_amount=0.005,
        max_amount=1,
    ):
        """Create an instance of VeilClient to interact with the veil.co API

        Keyword arguments:
        network_id -- numerable id of networkId convertible to `constants.NetworkId`
        web3_rpc_url -- string of the URL of the Web3 service
        private_key -- hex bytes or hex string of private key for signing transactions
            (must be convertible to `HexBytes`) (default: None)
        min_amount -- minimum amount of shares allowable in single transaction
        max_amount -- maximum amount of shares allowable in single transaction
        """
        super(VeilClient, self).__init__(
            network_id=network_id,
            web3_rpc_url=web3_rpc_url,
            private_key=private_key,
        )
        self._veil_api_url = NETWORK_INFO[self.network_id]["veil_api_url"]
        self._min_amount = min_amount
        self._max_amount = max_amount
        self._session_challenge = None
        self._session = None
        # cache markets by filter tuple
        self._markets = {}

    def _str_arg_append(self):
        """String to append to list of params for `__str__`"""
        return (
            f", authenticated={self._session is not None}"
            f", min_amount={self._min_amount}"
            f", max_amount={self._max_amount}"
        )

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
        raw_json=False,
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
        raw_json -- boolean of whether the result should be left as a raw json or
            converted to a list of `Market` objects (default: False)
        """
        if not raw_json and not force_refresh and self._markets is not None:
            markets = self._markets.get((channel, status, page, per_page))
            if markets is not None:
                return markets
        params = {}
        if channel:
            params["channel"] = channel
        if status:
            params["status"] = status
        markets = self._request_paginated(
            method="GET",
            url="{}markets".format(self._veil_api_url),
            params=params,
            page=page,
            per_page=per_page,
            raw_json=raw_json,
        )
        if not raw_json:
            markets = [Market(**m) for m in markets]
            self._markets[(channel, status, page, per_page)] = markets
        return markets

    def get_market(
        self,
        market_slug,
        force_refresh=False,
        raw_json=False,
    ):
        """Fetch a single market using the market "slug" identifier
        Note: Public endpoint, does not need an account

        Keyword arguments:
        market_slug -- string "slug" (relatively short human-readable identifier)
            from /markets API call
        force_refresh -- boolean of whether results should be fetched again
            from server or from in-memory cache (default: False)
        raw_json -- boolean of whether the result should be left as a raw json or
            converted to a `Market` object (default: False)
        """
        if not raw_json and not force_refresh and self._markets is not None:
            market = self._markets.get(market_slug)
            if market is not None:
                return market
        res = self._request(
            method="GET",
            url="{}markets/{}".format(self._veil_api_url, market_slug),
        )
        if not raw_json:
            res = Market(**res["data"])
            self._markets[market_slug] = res
        return res

    def get_feed_data(
        self,
        feed_name,
        scope="month",
        raw_json=False,
    ):
        """Fetch feed data using `Market.index`

        Keyword argument:
        feed_name -- string feed name from `Market.index`
        raw_json -- boolean of whether the result should be left as a raw json or
            converted to a `Market` object (default: False)
        """
        data_feed = self._request(
            method="GET",
            url="{}data_feeds/{}".format(self._veil_api_url, feed_name),
            params={"scope": scope},
        )
        if not raw_json:
            data_feed = DataFeed(**data_feed["data"])
        return data_feed

    def get_bids(
        self,
        market_slug,
        token_type,
        page=None,
        per_page=None,
        raw_json=False,
    ):
        """Fetch the long or short orders for a given market
        Note that long and short are mirror images of each other

        Keyword arguments:
        market_slug -- string "slug" (relatively short human-readable identifier)
            from /markets API call
        token_type --  value from `TokenType` enum (.e.g. "short", "long")
        page -- integer page number to get results from. Note that first page
            is at page=0 (default: None which means get all pages)
        per_page -- integer number of records per page (default: None and
            falls back to default value in `_request_paginated`)
        raw_json -- boolean of whether the result should be left as a raw json or
            converted to a bid `SideBook` object (default: False)
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
        if not raw_json:
            res = SideBook(side=OrderSide.BUY, entries=res)
        return res

    def get_asks(
        self,
        market_slug,
        token_type,
        page=None,
        per_page=None,
        raw_json=False,
    ):
        """Fetch the bids orders for a given long or short market
        Note that long and short are mirror images of each other

        Keyword arguments:
        market_slug -- string "slug" (relatively short human-readable identifier)
            from /markets API call
        token_type --  value from `TokenType` enum (e.g. "short", "long")
        page -- integer page number to get results from. Note that first page
            is at page=0 (default: None which means get all pages)
        per_page -- integer number of records per page (default: None and
            falls back to default value in `_request_paginated`)
        raw_json -- boolean of whether the result should be left as a raw json or
            converted to a ask `SideBook` object (default: False)
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
        if not raw_json:
            res = SideBook(side=OrderSide.SELL, entries=res)
        return res

    def get_order_fills(
        self,
        market_slug,
        token_type,
        page=None,
        per_page=None,
        raw_json=False,
    ):
        """Fetch the order fill history for a given long or short market
        Note that long and short are mirror images of each other

        Keyword arguments:
        market_slug -- string "slug" (relatively short human-readable identifier)
            from /markets API call
        token_type --  value from `TokenType` enum (e.g. "short", "long")
        page -- integer page number to get results from. Note that first page
            is at page=0 (default: None which means get all pages)
        per_page -- integer number of records per page (default: None and
            falls back to default value in `_request_paginated`)
        raw_json -- boolean of whether the result should be left as a raw json or
            converted to a `OrderFill` object (default: False)
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
        if not raw_json:
            res = [OrderFill(**order_fill) for order_fill in res]
        return res

    def post_order(
        self,
        market,
        token_type,
        side,
        amount,
        price,
        order_price_type=OrderPriceType.LIMIT,
        raw_json=False,
    ):
        """Get a Veil quote, sign the order on it and post the order

        Keyword arguments:
        market -- Market instance
        token_type --  value from `TokenType` enum (.e.g. "short", "long")
        side -- value from `OrderSide` enum (i.e. "buy", "sell")
        amount -- numeric-like token amount (1 means 1 share)
        price -- numeric-like price in ETH (i.e. between 0 and 1)
        order_price_type -- value from `OrderPriceType` enum (default: OrderPriceType.LIMIT)
        raw_json -- boolean of whether the result should be left as a raw json or
            converted to a `QuoteResponse` object (default: False)
        """
        quote = self._get_quote(
            market=market,
            token_type=token_type,
            side=side,
            amount=amount,
            price=price,
            order_price_type=order_price_type,
        )
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
        quote_id,
        signed_order,
        raw_json=False,
    ):
        """Post a signed order

        Keyword arguments:
        quote_id -- string id of the quote acquired from `get_quote()`
        signed_order -- instance of `ZxSignedOrder` that has been signed
        raw_json -- boolean of whether the result should be left as a raw json or
            converted to a `Order` object (default: False)
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
        if not raw_json:
            res = Order(**res["data"])
            res.zero_ex_order = signed_order
        return res

    def _get_quote(
        self,
        market,
        token_type,
        side,
        amount,
        price,
        order_price_type=OrderPriceType.LIMIT,
        raw_json=False,
    ):
        """Get the template for 0x order to sign

        Keyword arguments:
        market -- Market instance
        token_type --  value from `TokenType` enum (.e.g. "short", "long")
        side -- value from `OrderSide` enum (i.e. "buy", "sell")
        amount -- numeric-like token amount (1 means 1 share)
        price -- numeric-like price in ETH (i.e. between 0 and 1)
        order_price_type -- value from `OrderPriceType` enum (default: OrderPriceType.LIMIT)
        raw_json -- boolean of whether the result should be left as a raw json or
            converted to a `QuoteResponse` object (default: False)
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
        if not raw_json:
            res = QuoteResponse(**res["data"])
        return res

    def get_orders(
        self,
        market_slug,
        order_status=OrderStatus.OPEN,
        page=None,
        per_page=None,
        raw_json=False,
    ):
        """Fetch orders associated with the user for a given market

        Keyword arguments:
        market_slug -- string "slug" (relatively short human-readable identifier)
            from /markets API call
        order_status -- value from `OrderStatus` enum (default: OrderStats.OPEN)
        page -- integer page number to get results from. Note that first page
            is at page=0 (default: None which means get all pages)
        per_page -- integer number of records per page (default: None and
            falls back to default value in `_request_paginated`)
        raw_json -- boolean of whether the result should be left as a raw json or
            converted to a list of `Order` objects (default: False)
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
            raw_json=raw_json,
        )
        if not raw_json:
            orders = [Order(**order) for order in orders]
        return orders

    def cancel_order(
        self,
        order_id,
        raw_json=False,
    ):
        """Cancel an order using its uid

        Keyword argument:
        order_id -- string `uid` from `QuoteResponse` or `Order`
        raw_json -- boolean of whether the result should be left as a raw json or
            converted to a `Order` object (default: False)
        """
        res = res = self._request(
            method="DELETE",
            url="{}orders/{}".format(self._veil_api_url, order_id),
            requires_session=True,
        )
        if not raw_json:
            res = Order(**res["data"])
        return res

    def get_balances(
        self,
        market_slug,
        raw_json=False,
    ):
        """Fetch position balances associated with the user for a given market

        Keyword arguments:
        market_slug -- string "slug" (relatively short human-readable identifier)
            from /markets API call
        raw_json -- boolean of whether the result should be left as a raw json or
            converted to a `MarketBalances` object (default: False)
        """
        balances = self._request(
            method="GET",
            url="{}markets/{}/balances".format(self._veil_api_url, market_slug),
            requires_session=True,
        )
        if not raw_json:
            balances = balances["data"]
            balances["slug"] = market_slug
            balances = MarketBalances(**balances)
        return balances

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
        elif method == "DELETE":
            res = requests.delete(url, headers=headers)
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
        LOGGER.debug(res.content)
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
        raw_json=False,
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
        raw_json -- boolean of whether the result should be left as a raw json or
            converted to a `Quote` object (default: False)
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
