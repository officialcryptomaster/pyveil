"""
0x Web3 Utilities

author: officialcryptomaster@gmail.com
"""
from decimal import Decimal
from enum import Enum
from typing import Optional, Union

from eth_utils import keccak, to_checksum_address
from hexbytes import HexBytes
from zero_ex.json_schemas import assert_valid
from zero_ex.contract_artifacts import abi_by_name

from utils.miscutils import (
    try_, assert_like_integer, now_epoch_msecs,
    epoch_secs_to_local_time_str, epoch_msecs_to_local_time_str)
from utils.web3utils import (
    Web3Client, TxParams, NetworkId,
    get_clean_address_or_throw, NULL_ADDRESS)

ZX_CONTRACT_ADDRESSES = {
    NetworkId.MAINNET: {
        "exchange": "0x4f833a24e1f95d70f028921e27040ca56e09ab0b",
        "erc20_proxy": "0x2240dab907db71e64d3e0dba4800c83b5c502d4e",
        "erc721_proxy": "0x208e41fb445f1bb1b6780d58356e81405f3e6127",
        "asset_proxy_owner": "0x17992e4ffb22730138e4b62aaa6367fa9d3699a6",
        "forwarder": "0x5468a1dc173652ee28d249c271fa9933144746b1",
        "order_validator": "0x9463e518dea6810309563c81d5266c1b1d149138",
        "zrx_token": "0xe41d2489571d322189246dafa5ebde1f4699f498",
        "ether_token": "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2",
    },
    NetworkId.ROPSTEN: {
        "exchange": "0x4530c0483a1633c7a1c97d2c53721caff2caaaaf",
        "erc20_proxy": "0xb1408f4c245a23c31b98d2c626777d4c0d766caa",
        "erc721_proxy": "0xe654aac058bfbf9f83fcaee7793311dd82f6ddb4",
        "asset_proxy_owner": "0xf5fa5b5fed2727a0e44ac67f6772e97977aa358b",
        "forwarder": "0x2240dab907db71e64d3e0dba4800c83b5c502d4e",
        "order_validator": "0x90431a90516ab49af23a0530e04e8c7836e7122f",
        "zrx_token": "0xff67881f8d12f372d91baae9752eb3631ff0ed00",
        "ether_token": "0xc778417e063141139fce010982780140aa0cd5ab",
    },
    NetworkId.RINKEBY: {
        "exchange": "0xbce0b5f6eb618c565c3e5f5cd69652bbc279f44e",
        "erc20_proxy": "0x2f5ae4f6106e89b4147651688a92256885c5f410",
        "erc721_proxy": "0x7656d773e11ff7383a14dcf09a9c50990481cd10",
        "asset_proxy_owner": "0xe1703da878afcebff5b7624a826902af475b9c03",
        "forwarder": "0x2d40589abbdee84961f3a7656b9af7adb0ee5ab4",
        "order_validator": "0x0c5173a51e26b29d6126c686756fb9fbef71f762",
        "zrx_token": "0x8080c7e4b81ecf23aa6f877cfbfd9b0c228c6ffa",
        "ether_token": "0xc778417e063141139fce010982780140aa0cd5ab",
    },
    NetworkId.KOVAN: {
        "exchange": "0x35dd2932454449b14cee11a94d3674a936d5d7b2",
        "erc20_proxy": "0xf1ec01d6236d3cd881a0bf0130ea25fe4234003e",
        "erc721_proxy": "0x2a9127c745688a165106c11cd4d647d2220af821",
        "asset_proxy_owner": "0x2c824d2882baa668e0d5202b1e7f2922278703f8",
        "forwarder": "0x17992e4ffb22730138e4b62aaa6367fa9d3699a6",
        "order_validator": "0xb389da3d204b412df2f75c6afb3d0a7ce0bc283d",
        "zrx_token": "0x2002d3812f58e35f0ea1ffbf80a75a38c32175fa",
        "ether_token": "0xd0a1e359811322d97991e03f863a0c30c2cf029c",
    },
    NetworkId.GANACHE: {
        "exchange": "0x48bacb9266a570d521063ef5dd96e61686dbe788",
        "erc20_proxy": "0x1dc4c1cefef38a777b15aa20260a54e584b16c48",
        "erc721_proxy": "0x1d7022f5b17d2f8b695918fb48fa1089c9f85401",
        "asset_proxy_owner": "0x34d402f14d58e001d8efbe6585051bf9706aa064",
        "forwarder": "0xb69e673309512a9d726f87304c6984054f87a93b",
        "order_validator": "0xe86bb98fcf9bff3512c74589b78fb168200cc546",
        "zrx_token": "0x871dd7c2b4b25e1aa18728e9d5f2af4c4e431f5c",
        "ether_token": "0x0b1ba0af832d7c05fd64161e0db78e85978e8082",
    },
}

EIP191_HEADER = b"\x19\x01"
ERC20_PROXY_ID = '0xf47261b0'
ERC721_PROXY_ID = '0x02571792'


EIP712_DOMAIN_SEPARATOR_SCHEMA_HASH = keccak(
    b"EIP712Domain(string name,string version,address verifyingContract)"
)


EIP712_ORDER_SCHEMA_HASH = keccak(
    b"Order("
    + b"address makerAddress,"
    + b"address takerAddress,"
    + b"address feeRecipientAddress,"
    + b"address senderAddress,"
    + b"uint256 makerAssetAmount,"
    + b"uint256 takerAssetAmount,"
    + b"uint256 makerFee,"
    + b"uint256 takerFee,"
    + b"uint256 expirationTimeSeconds,"
    + b"uint256 salt,"
    + b"bytes makerAssetData,"
    + b"bytes takerAssetData"
    + b")"
)


EIP712_DOMAIN_STRUCT_HEADER = (
    EIP712_DOMAIN_SEPARATOR_SCHEMA_HASH
    + keccak(b"0x Protocol")
    + keccak(b"2")
)


class ZxOrderStatus(Enum):
    """OrderStatus codes used by 0x contracts"""
    INVALID = 0  # Default value
    INVALID_MAKER_ASSET_AMOUNT = 1  # Order does not have a valid maker asset amount
    INVALID_TAKER_ASSET_AMOUNT = 2  # Order does not have a valid taker asset amount
    FILLABLE = 3  # Order is fillable
    EXPIRED = 4  # Order has already expired
    FULLY_FILLED = 5  # Order is fully filled
    CANCELLED = 6  # Order has been cancelled


class ZxOrderInfo:  # pylint: disable=too-few-public-methods
    """A Web3-compatible representation of the `Exchange.OrderInfo`."""

    __name__ = "OrderInfo"

    def __init__(
        self,
        zx_order_status,
        order_hash,
        order_taker_asset_filled_amount
    ):
        """Create an instance of Exchange.OrderInfo struct.

        Args:
            zx_order_status (:class:`ZxOrderStatus`): order status
            order_hash (:class:`HexBytes` or bytes): order hash
            order_taker_assert_filled_amount (int): order taker asset filled
                amount
        """
        self.zx_order_status = ZxOrderStatus(zx_order_status)
        self.order_hash = HexBytes(order_hash)
        self.order_taker_asset_filled_amount = int(order_taker_asset_filled_amount)

    def __str__(self):
        return (
            f"[{self.__name__}]"
            f"({try_(ZxOrderStatus, self.zx_order_status)}"
            f", {self.order_hash.hex()}"
            f", filled_amount={self.order_taker_asset_filled_amount})")

    __repr__ = __str__


class ZxSignedOrder:  # pylint: disable=too-many-public-methods
    """0x Signed Order model

    This object will keep the database-friendly formats in member variables
    starting with underscore, and provide property setter and getters for
    getting the values in useful formats
    """

    __name__ = "ZxSignedOrder"

    def __init__(self, **kwargs):
        """Create an instance of ZxSignedOrder."""
        # initialize all serialized (i.e. DB storable) columns as members
        # ending with underscore.
        self.hash_ = None
        self.maker_address_ = None
        self.taker_address_ = None
        self.fee_recipient_address_ = None
        self.sender_address_ = None
        self.exchange_address_ = None
        self.maker_asset_amount_ = None
        self.taker_asset_amount_ = None
        self.maker_fee_ = None
        self.taker_fee_ = None
        self.salt_ = None
        self.expiration_time_seconds_ = None
        self.maker_asset_data_ = None
        self.taker_asset_data_ = None
        self.signature_ = None
        # book-keeping fields
        self.created_at_msecs_ = None
        self.bid_price_ = None
        self.ask_price_ = None
        self.sort_price_ = None

        # assign keyword args and default values
        self._created_at_msecs_ = kwargs.get("created_at_msecs") or now_epoch_msecs()
        self.hash_ = kwargs.get("hash") or None
        self.maker_address = kwargs.get("maker_address") or NULL_ADDRESS
        self.taker_address = kwargs.get("taker_address") or NULL_ADDRESS
        self.fee_recipient_address = kwargs.get("fee_recipient_address") or NULL_ADDRESS
        self.sender_address = kwargs.get("sender_address") or NULL_ADDRESS
        self.exchange_address = kwargs.get("exchange_address") or NULL_ADDRESS
        self.maker_asset_amount = kwargs.get("maker_asset_amount") or "0"
        self.taker_asset_amount = kwargs.get("taker_asset_amount") or "0"
        self.taker_fee = kwargs.get("taker_fee") or "0"
        self.maker_fee = kwargs.get("maker_fee") or "0"
        self.salt = kwargs.get("salt") or "0"
        # default expiry to one minute after creation
        self.expiration_time_seconds = kwargs.get("expiration_time_seconds") \
            or self._created_at_msecs_ / 1000. + 60
        self.maker_asset_data = kwargs.get("maker_asset_data") or None
        self.taker_asset_data = kwargs.get("taker_asset_data") or None
        self.signature_ = kwargs.get("signature") or None

    def __str__(self):
        return (
            f"[{self.__name__}]"
            f"(hash={self.hash}"
            f", maker_address={self.maker_address}"
            f", taker_address={self.taker_address}"
            f", fee_recipient_address={self.fee_recipient_address}"
            f", sender_address={self.sender_address}"
            f", exchange_address={self.exchange_address}"
            f", maker_asset_amount={self.maker_asset_amount}"
            f", taker_asset_amount={self.taker_asset_amount}"
            f", maker_fee={self.maker_fee}"
            f", taker_fee={self.taker_fee}"
            f", salt={self.salt}"
            f", maker_asset_data={self.maker_asset_data}"
            f", taker_asset_data={self.taker_asset_data}"
            f", expires={self.expiration_time}"
            f", signature={self.signature}"
            ")"
        )

    __repr__ = __str__

    @property
    def hash(self):
        """Get hash of the order with lazy evaluation."""
        if self.hash_ is None:
            try_(self.update_hash)
        return self.hash_

    @property
    def maker_address(self):
        """Get maker address as hex string."""
        return self.maker_address_

    @maker_address.setter
    def maker_address(self, value):
        """Set maker address with validation.

        Keyword argument:
        value -- hex string of maker address
        """
        self.maker_address_ = None if value is None else get_clean_address_or_throw(value)

    @property
    def taker_address(self):
        """Get taker address as hex string."""
        return self.taker_address_

    @taker_address.setter
    def taker_address(self, value):
        """Set taker address with validation.

        Keyword argument:
        value -- hex string of taker address
        """
        self.taker_address_ = None if value is None else get_clean_address_or_throw(value)

    @property
    def fee_recipient_address(self):
        """Get fee recipient address as hex string."""
        return self.fee_recipient_address_

    @fee_recipient_address.setter
    def fee_recipient_address(self, value):
        """Set fee recipient address with validation.

        Keyword argument:
        value -- hex string of fee recipient address
        """
        self.fee_recipient_address_ = None if value is None else get_clean_address_or_throw(value)

    @property
    def sender_address(self):
        """Get sender address as hex string."""
        return self.sender_address_

    @sender_address.setter
    def sender_address(self, value):
        """Set sender address with validation.

        Keyword argument:
        value -- hex string of sender address
        """
        self.sender_address_ = None if value is None else get_clean_address_or_throw(value)

    @property
    def exchange_address(self):
        """Get exchange address as hex string."""
        return self.exchange_address_

    @exchange_address.setter
    def exchange_address(self, value):
        """Set exchange address with validation.

        Keyword argument:
        value -- hex string of exchange contract address
        """
        self.exchange_address_ = None if value is None else get_clean_address_or_throw(value)

    @property
    def maker_asset_amount(self):
        """Get maker asset amount as integer in base units."""
        return int(self.maker_asset_amount_)

    @maker_asset_amount.setter
    def maker_asset_amount(self, value):
        """Set maker asset amount in base units.

        Keyword argument:
        value -- integer-like maker asset amount in base units
        """
        assert_like_integer(value)
        self.maker_asset_amount_ = "{:.0f}".format(Decimal(value))
        self.update_bid_price()
        self.update_ask_price()

    @property
    def taker_asset_amount(self):
        """Get taker asset amount as integer in base units."""
        return int(self.taker_asset_amount_)

    @taker_asset_amount.setter
    def taker_asset_amount(self, value):
        """Set taker asset amount in base units.

        Keyword argument:
        value -- integer-like taker asset amount in base units
        """
        assert_like_integer(value)
        self.taker_asset_amount_ = "{:.0f}".format(Decimal(value))
        self.update_bid_price()
        self.update_ask_price()

    @property
    def maker_fee(self):
        """Get maker fee as integer in base units."""
        return int(self.maker_fee_)

    @maker_fee.setter
    def maker_fee(self, value):
        """Set maker fee in base units.

        Keyword argument:
        value -- integer-like maker fee in base units
        """
        assert_like_integer(value)
        self.maker_fee_ = "{:.0f}".format(Decimal(value))

    @property
    def taker_fee(self):
        """Get taker fee as integer in base units."""
        return int(self.taker_fee_)

    @taker_fee.setter
    def taker_fee(self, value):
        """Set taker fee in base units.

        Keyword argument:
        value -- integer-like taker fee in base units
        """
        assert_like_integer(value)
        self.taker_fee_ = "{:.0f}".format(Decimal(value))

    @property
    def salt(self):
        """Get salt as integer."""
        return int(self.salt_)

    @salt.setter
    def salt(self, value):
        """Set salt from integer-like.

        Keyword argument:
        value -- integer-like salt value
        """
        assert_like_integer(value)
        self.salt_ = "{:.0f}".format(Decimal(value))

    @property
    def expiration_time(self):
        """Get expiration as naive datetime."""
        return try_(epoch_secs_to_local_time_str, self.expiration_time_seconds_)

    @property
    def expiration_time_seconds(self):
        """Get expiration time in seconds since epoch."""
        return self.expiration_time_seconds_

    @expiration_time_seconds.setter
    def expiration_time_seconds(self, value):
        """Set expiration time secs from numeric-like.

        Keyword argument:
        value -- numeric-like expiration time in seconds since epoch
        """
        self.expiration_time_seconds_ = int("{:.0f}".format(Decimal(value)))

    @property
    def maker_asset_data(self):
        """Get asset data as HexBytes."""
        return self.maker_asset_data_

    @maker_asset_data.setter
    def maker_asset_data(self, value):
        """Set maker asset data.

        Keyword argument:
        value -- hexbytes-like maker asset data
        """
        self.maker_asset_data_ = HexBytes(value).hex() if value is not None else None

    @property
    def taker_asset_data(self):
        """Get asset data as hex string."""
        return self.taker_asset_data_

    @taker_asset_data.setter
    def taker_asset_data(self, value):
        """Set taker asset data

        Keyword argument:
        value -- hexbytes-like taker asset data
        """
        self.taker_asset_data_ = HexBytes(value).hex() if value is not None else None

    @property
    def signature(self):
        """Return the signaure of the SignedOrder."""
        return self.signature_

    @signature.setter
    def signature(self, value):
        """Set the signature."""
        self.signature_ = HexBytes(value).hex() if value is not None else None

    @property
    def created_at_msecs(self):
        """Get creation time in milliseconds since epoch."""
        return self.created_at_msecs_

    @property
    def created_at(self):
        """Get creation time timestamp as naive :class:`DateTime`."""
        return try_(epoch_msecs_to_local_time_str, self.created_at_msecs_)

    @property
    def bid_price(self):
        """Get bid price as a Decimal."""
        return try_(Decimal, self.bid_price_, default_=Decimal(0))

    @property
    def ask_price(self):
        """Get ask price as a Decimal."""
        return try_(Decimal, self.ask_price_, default_=Decimal("9" * 32))

    @property
    def sort_price(self):
        """Get sort price.
        This is useful for full set order which result in a mix of bids and asks
        (hint: make use of `set_bid_price_as_sort_price` and its equivalent
        `set_bid_price_as_sort_price`)
        """
        return Decimal(self.sort_price_)

    def update_hash(self):
        """Update the hash of the order and return the order."""
        self.hash_ = self.get_order_hash(self.to_json())
        return self

    def update(self):
        """Call all update functions for order and return order."""
        self.update_hash()
        return self

    def update_bid_price(self):
        """Bid price is price of taker asset per unit of maker asset.
        (i.e. price of taker asset which maker is bidding to buy)
        """
        try:
            self.bid_price_ = "{:032.18f}".format(
                Decimal(self.taker_asset_amount) / Decimal(self.maker_asset_amount))
        except:  # noqa E722 pylint: disable=bare-except
            self.bid_price_ = "0" * 32
        return self

    def update_ask_price(self):
        """Ask price is price of maker asset per unit of taker asset.
        (i.e. price of maker asset the maker is asking to sell)
        """
        try:
            self.ask_price_ = "{:032.18f}".format(
                Decimal(self.maker_asset_amount) / Decimal(self.taker_asset_amount))
        except:  # noqa E722 pylint: disable=bare-except
            self.ask_price_ = "9" * 32
        return self

    def set_bid_as_sort_price(self):
        """Set the `sort_price_` field to be the `bid_price_`.
        This can be useful for sorting full set orders
        """
        self.sort_price_ = self.bid_price_
        return self

    def set_ask_as_sort_price(self):
        """Set the `_sort_price` field to be the `ask_price_`.
        This can be useful for sorting full set orders
        """
        self.sort_price_ = self.ask_price_
        return self

    def to_json(
        self,
        include_hash=False,
        include_signature=True,
        include_exchange_address=None,
        for_web3=False,
    ):
        """Get a json representation of the SignedOrder.

        Args:
            include_hash (bool): whether to include the hash field
                (default: False)
            include_signature (bool): whether to include the signature
                (default: True)
            include_exchange_address (bool): whether to include the
                exchange_address field (default: None, which means if set to
                False for web3 and set to True for non-web3 use case)
            for_web3 (bool): whether the value types should be changed
                for calling 0x contracts through web3 library (default:
                False)
        """
        if for_web3:
            if include_exchange_address is None:
                include_exchange_address = False
            order = {
                "makerAddress": to_checksum_address(self.maker_address_),
                "takerAddress": to_checksum_address(self.taker_address_),
                "feeRecipientAddress": to_checksum_address(self.fee_recipient_address_),
                "senderAddress": to_checksum_address(self.sender_address_),
                "makerAssetAmount": int(self.maker_asset_amount_),
                "takerAssetAmount": int(self.taker_asset_amount_),
                "makerFee": int(self.maker_fee_),
                "takerFee": int(self.taker_fee_),
                "salt": int(self.salt_),
                "expirationTimeSeconds": int(self.expiration_time_seconds_),
                "makerAssetData": HexBytes(self.maker_asset_data_),
                "takerAssetData": HexBytes(self.taker_asset_data_),
            }
            if include_hash:
                order["hash"] = HexBytes(self.hash)
            if include_signature:
                order["signature"] = HexBytes(self.signature)
            if include_exchange_address:
                order["exchangeAddress"] = HexBytes(self.exchange_address_)
        else:
            if include_exchange_address is None:
                include_exchange_address = True
            order = {
                "makerAddress": self.maker_address_,
                "takerAddress": self.taker_address_,
                "feeRecipientAddress": self.fee_recipient_address_,
                "senderAddress": self.sender_address_,
                "makerAssetAmount": self.maker_asset_amount_,
                "takerAssetAmount": self.taker_asset_amount_,
                "makerFee": self.maker_fee_,
                "takerFee": self.taker_fee_,
                "salt": self.salt_,
                "expirationTimeSeconds": self.expiration_time_seconds_,
                "makerAssetData": self.maker_asset_data_,
                "takerAssetData": self.taker_asset_data_,
            }
            if include_hash:
                order["hash"] = self.hash
            if include_signature:
                order["signature"] = self.signature_
            if include_exchange_address:
                order["exchangeAddress"] = self.exchange_address_
        return order

    @classmethod
    def get_order_hash(cls, order_json):
        """Returns hex string hash of 0x order

        Args:
            order_json (dict): a dict conforming to "/signedOrderSchema"
                or "/orderSchema" (dependign on whether `include_signature`
                is set to True or False) schemas can be found
                `here <https://github.com/0xProject/0x-monorepo/tree/development/
                packages/json-schemas/schemas>`__

        Returns:
            (str) order hash
        """
        order = order_json
        eip712_domain_struct_hash = keccak(
            EIP712_DOMAIN_STRUCT_HEADER
            + HexBytes(order["exchangeAddress"]).rjust(32, b"\0")
        )

        eip712_order_struct_hash = keccak(
            EIP712_ORDER_SCHEMA_HASH
            + HexBytes(order["makerAddress"]).rjust(32, b"\0")
            + HexBytes(order["takerAddress"]).rjust(32, b"\0")
            + HexBytes(order["feeRecipientAddress"]).rjust(32, b"\0")
            + HexBytes(order["senderAddress"]).rjust(32, b"\0")
            + int(order["makerAssetAmount"]).to_bytes(32, byteorder="big")
            + int(order["takerAssetAmount"]).to_bytes(32, byteorder="big")
            + int(order["makerFee"]).to_bytes(32, byteorder="big")
            + int(order["takerFee"]).to_bytes(32, byteorder="big")
            + int(order["expirationTimeSeconds"]).to_bytes(32, byteorder="big")
            + int(order["salt"]).to_bytes(32, byteorder="big")
            + keccak(HexBytes(order["makerAssetData"]))
            + keccak(HexBytes(order["takerAssetData"]))
        )

        return "0x" + keccak(
            EIP191_HEADER
            + eip712_domain_struct_hash
            + eip712_order_struct_hash
        ).hex()

    @classmethod
    def from_json(
        cls,
        order_json,
        check_validity=False,
        include_signature=True,
    ):
        """Given a json representation of a signed order, return a SignedOrder object

        Args:
            order_json (dict): a dict conforming to "/signedOrderSchema"
                or "/orderSchema" (dependign on whether `include_signature`
                is set to True or False) schemas can be found
                `here <https://github.com/0xProject/0x-monorepo/tree/development/
                packages/json-schemas/schemas>`__
            check_validity (bool): whether we should do an explicit check
                to make sure the passed in dict adheres to the required
                schema (default: True)
            include_signature (bool): whether the object is expected to have
                the signature on it or not. This will affect whether
                "/signedOrderSchema" or "/orderSchema" is used for validation
                (default: True)
        """
        order = cls()
        if check_validity:
            if include_signature:
                assert_valid(order_json, "/signedOrderSchema")
            else:
                assert_valid(order_json, "/orderSchema")
        order.maker_address = order_json["makerAddress"]
        order.taker_address = order_json["takerAddress"]
        order.maker_fee = order_json["makerFee"]
        order.taker_fee = order_json["takerFee"]
        order.sender_address = order_json["senderAddress"]
        order.maker_asset_amount = order_json["makerAssetAmount"]
        order.taker_asset_amount = order_json["takerAssetAmount"]
        order.maker_asset_data = order_json["makerAssetData"]
        order.taker_asset_data = order_json["takerAssetData"]
        order.salt = order_json["salt"]
        order.exchange_address = order_json["exchangeAddress"]
        order.fee_recipient_address = order_json["feeRecipientAddress"]
        order.expiration_time_seconds = order_json["expirationTimeSeconds"]
        if include_signature:
            order.signature = order_json["signature"]
        order.update()
        return order


class ZxWeb3Client(Web3Client):
    """Client for interacting with 0x contracts."""

    __name__ = "ZxWeb3Client"

    def __init__(
        self,
        network_id: int,
        web3_rpc_url: str,
        private_key: Optional[Union[HexBytes, str]] = None,
    ):
        """Create an instance of the ZxWeb3Client.

        Args:
            network_id (int): id of network from :class:`NetworkId`
            web3_rpc_url (str): URL of the Web3 service
            private_key (:class:`HexBytes` or strstr): hex bytes or hexstr
                of private key for signing transactions (must be convertible
                to :class:`HexBytes`) (default: None)
        """
        super(ZxWeb3Client, self).__init__(
            network_id=network_id,
            web3_rpc_url=web3_rpc_url,
            private_key=private_key,
        )
        self._contract_addressess = \
            ZX_CONTRACT_ADDRESSES[NetworkId(self._network_id)]
        self._zx_exchange = None

    @property
    def exchange_address_checksumed(self):
        """Get checksummed address of the 0x Exchange contract."""
        return to_checksum_address(self._contract_addressess["exchange"])

    @property
    def zx_exchange(self):
        """Get an instance of the 0x Exchange contract."""
        if self._zx_exchange is None:
            self._zx_exchange = self.web3_eth.contract(
                address=self.exchange_address_checksumed,
                abi=abi_by_name("Exchange"))
        return self._zx_exchange

    def sign_hash_zx_compat(self, hash_hex: Union[HexBytes, str]) -> str:
        """Get a zx-compatible signature from signing a hash_hex with eth-sign.

        Args:
            hash_hex (:class:`HexBytes` or hashstr): hash to sign

        Returns:
            (str) 0x-compatible signature of hash
        """
        ec_signature = self.sign_hash(hash_hex)
        return self.get_zx_signature_from_ec_signature(ec_signature=ec_signature)

    @staticmethod
    def get_zx_signature_from_ec_signature(ec_signature) -> str:
        """Get a hexstr 0x-compatible signature from an eth-sign ec_signature

        0x signature is a hexstr made from the concatenation of the hexstr of the "v",
        r", and "s" parameters of an ec_signature and ending with constant "03" to
        indicate "eth-sign" was used.
        The "r" and "s" parts of the signature need to each represent 32 bytes
        and so will be righ-justified with "0" padding on the left (i.e. "r" and "s"
        will be strings of 64 hex characters each, which means no leading "0x")

        Args:
            ec_singature (dict): A dict containing "r", "s" and "v"
                parameters of an elliptic curve signature as integers

        Returns:
            (str) 0x-compatible hash signature
        """
        v = hex(ec_signature["v"])  # pylint: disable=invalid-name
        r = HexBytes(ec_signature["r"]).rjust(32, b"\0").hex()  # pylint: disable=invalid-name
        s = HexBytes(ec_signature["s"]).rjust(32, b"\0").hex()  # pylint: disable=invalid-name
        # append "03" to specify signature type of eth-sign
        return v + r + s + "03"

    def cancel_zx_order(
        self,
        zx_signed_order: ZxSignedOrder,
        tx_params: TxParams = None,
    ) -> Union[HexBytes, bytes]:
        """Call the cancelOrder function of the 0x Exchange contract

        Args:
            zx_signed_order (:class:`ZxSignedOrder`): order to cancel
            tx_params (:class:`TxParams`): transaction options (default:
                None)

        Returns:
            (:class:`HexBytes`) transaction hash
        """
        order = zx_signed_order.to_json(for_web3=True)
        func = self.zx_exchange.functions.cancelOrder(order)
        return self._invoke_function_call(
            func, tx_params=tx_params, view_only=False)

    def fill_zx_order(
        self,
        zx_signed_order: ZxSignedOrder,
        taker_fill_amount: int,
        base_unit_decimals: int = 18,
        tx_params: TxParams = None,
    ) -> Union[HexBytes, bytes]:
        """Call the fillOrder function of the 0x Exchange contract.

        Args:
            zx_signed_order (:class:`ZxSignedOrder`): order to fill
            taker_fill_amount (int): amount of taker asset (will be converted
                to base units by multiplying by 10**base_unit_decimals)
            base_unit_decimals (int): number of base unit decimals (default:
                18)
            tx_params (:class:`TxParams`): transaction options (default:
                None)

        Returns:
            (:class:`HexBytes`) transaction hash
        """
        signed_order = zx_signed_order.to_json(for_web3=True)
        signature = HexBytes(zx_signed_order.signature)
        taker_fill_amount = int(taker_fill_amount * 10**base_unit_decimals)
        func = self.zx_exchange.functions.fillOrder(
            signed_order,
            taker_fill_amount,
            signature
        )
        return self._invoke_function_call(
            func, tx_params=tx_params, view_only=False)
