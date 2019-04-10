"""
Web3 Utilities

author: officialcryptomaster@gmail.com
"""
from enum import Enum
import re
from typing import Optional, Union
from decimal import Decimal

import attr
from hexbytes import HexBytes
from eth_account.messages import defunct_hash_message
from eth_utils import to_checksum_address
from web3 import Web3, HTTPProvider


ETH_BASE_UNIT_DECIMALS = 18
NULL_ADDRESS = "0x0000000000000000000000000000000000000000"

RE_ADDRESS = re.compile("^(0x)?[0-9a-f]{40}$")


class NetworkId(Enum):
    """Enumeration of possible Network IDs."""
    MAINNET = 1
    ROPSTEN = 3
    RINKEBY = 4
    KOVAN = 42
    GANACHE = 50


def assert_valid_address(address: str):
    """Assert address is valid hex string

    Args:
        address (str): hex-like address
    """
    assert RE_ADDRESS.match(address.lower()), "address invalid format"


def assert_valid_address_or_none(address: str):
    """Assert address is a valid hex string or None.

    Args:
        address (str): hex-like address
    """
    assert address is None or RE_ADDRESS.match(address.lower()), \
        "address valid format"


def get_clean_address_or_throw(address: str) -> str:
    """Get a clean 42 character address with leading '0x' throw

    Args:
        address (str): hex-like address
    """
    if not isinstance(address, str):
        address = HexBytes(address).rjust(10, b"\0").hex()
    if not RE_ADDRESS.match(address.lower()):
        raise TypeError("address looks invalid: '{}'".format(address))
    if not address.startswith("0x"):
        address = "0x" + address
    return address


def get_hexstr_or_throw(hexstr_like) -> str:
    """Get a hex string with leading '0x' or throw

    Args:
        hexstr_like (hexlike): Either string that looks like hex or an object
        which HexBytes can turn into a hex string
    """
    return HexBytes(hexstr_like).hex()


def to_wei(
        numlike: Union[Decimal, int, float, str],
        decimals: int = ETH_BASE_UNIT_DECIMALS) -> int:
    """convert a numlike from regular units to integer base Wei.

    Keyword arguments:
        numlike (NumLike): something that can be converted to Decimal
        decimals (int): integer number of decimal places in the base unit
    """
    if not isinstance(numlike, Decimal):
        numlike = Decimal(numlike)
    if numlike == 0:
        return 0
    if not isinstance(decimals, int):
        decimals = int(str(decimals))
    # Note that round(numlike * 10 ** decimal) is dangerous as it loses
    # precision
    numlike = f"{{:.{decimals}f}}".format(numlike)
    return int(numlike[:-decimals-1] + numlike[-decimals:])


def from_wei(
        intlike: Union[Decimal, int, str],
        decimals: int = ETH_BASE_UNIT_DECIMALS) -> Decimal:
    """convert an intlike from integer base unit Wei to regular units.

    Args:
        intlike (IntLike): something that can be converted to Decimal
        decimals (int): integer number of decimal places in the base unit
    """
    if not isinstance(intlike, int):
        intlike = int(str(intlike))
    if intlike == 0:
        return Decimal(0)
    if not isinstance(decimals, int):
        decimals = int(str(decimals))
    intlike = f"{{:0{decimals}d}}".format(intlike)
    return Decimal(f"{intlike[:-decimals]}.{intlike[-decimals:]}")


@attr.s(kw_only=True)
class TxParams:
    """Transaction parameters for use with contract wrappers.

    Attributes:
        from_ (str): account address to initiate tx from (default: None)
        value (int): amount of ETH in Wei (default: None)
        gas (int): max amount of ETH in Wei for gas (default: None)
        gasPrice (int): unit price of Gas in Wei (default: None)
        none (int): nonce for account (default: None)
    """

    from_: Optional[str] = attr.ib(default=None)
    value: Optional[int] = attr.ib(
        default=None, converter=attr.converters.optional(int)
    )
    gas: Optional[int] = attr.ib(
        default=None, converter=attr.converters.optional(int)
    )
    gasPrice: Optional[int] = attr.ib(
        default=None, converter=attr.converters.optional(int)
    )
    nonce: Optional[int] = attr.ib(
        default=None, converter=attr.converters.optional(int)
    )

    def as_dict(self):
        """Get transaction params as dict appropriate for web3."""
        res = {k: v for k, v in attr.asdict(self).items() if v is not None}
        if "from_" in res:
            res["from"] = res["from_"]
            del res["from_"]
        return res


class Web3Client:
    """Client for interacting with Web3."""

    __name__ = "Web3Client"

    def __init__(
        self,
        network_id: int,
        web3_rpc_url: str,
        private_key: Optional[Union[HexBytes, str]] = None,
    ):
        """Create an instance of the Web3Client.

        Args:
            network_id (int): id of network from :class:`NetworkId`
            web3_rpc_url (str): URL of the Web3 service
            private_key (:class:`HexBytes` or strstr): hex bytes or hexstr
                of private key for signing transactions (must be convertible
                to :class:`HexBytes`) (default: None)
        """
        self._network_id = NetworkId(int(network_id)).value
        self._web3_rpc_url = web3_rpc_url
        self._private_key: Optional[HexBytes] = None
        self._web3_provider = None
        self._web3_instance = None
        self._web3_eth = None
        self._account = None
        self._account_address: Optional[str] = None
        if private_key:
            self.private_key = private_key

    def __str__(self):
        return (
            f"[{self.__name__}]"
            f"(network:{self.network_id}"
            f", web3_rpc_url={self._web3_rpc_url}"
            f", account_addres={self.account_address}"
            f"{self._str_arg_append()})"
        )

    __repr__ = __str__

    def _str_arg_append(self):  # pylint: disable=no-self-use
        """String to append to list of params for `__str__`."""
        return ""

    @property
    def network_id(self) -> NetworkId:
        """Get network id as :class:`NetworkId` enum."""
        return NetworkId(self._network_id)

    @property
    def private_key(self) -> Optional[str]:
        """Get the private key as :class:`HexBytes`."""
        if self._private_key:
            # equivalent of binascii.hexlify(self._private_key).decode("utf-8").lower()
            return self._private_key.hex()
        return None

    @private_key.setter
    def private_key(self, value: Union[HexBytes, str]):
        """Set private key as :class:`HexBytes`, and update the account.

        Args:
            value (:class:`HexBytes` or hexstr): private key for signing
                transactions (must be convertible to `HexBytes`)
        """
        # Use HexBytes instead of binascii.a2b_hex for convenience
        self._private_key = HexBytes(value)
        self._account_address = self.account_address

    @property
    def web3_provider(self):
        """Get a Web3 HTTPProvider instance with lazy instantiation."""
        if not self._web3_provider:
            if self._web3_rpc_url:
                self._web3_provider = HTTPProvider(self._web3_rpc_url)
        return self._web3_provider

    @property
    def web3_instance(self):
        """Get a Web3 instance with lazy instantiation."""
        if not self._web3_instance:
            web3_provider = self.web3_provider
            if self.web3_provider:
                self._web3_instance = Web3(web3_provider)
                self._web3_eth = self._web3_instance.eth  # pylint: disable=no-member
        return self._web3_instance

    @property
    def web3_eth(self):
        """Get the eth member of the Web3 instance with lazy instantiation."""
        if not self._web3_eth:
            web3_instance = self.web3_instance
            if web3_instance:
                self._web3_eth = web3_instance.eth  # pylint: disable=no-member
        return self._web3_eth

    @property
    def account(self):
        """Get the Web3 account object associated with the private key."""
        if not self._account:
            if self._private_key:
                web3_eth = self.web3_eth
                self._account = web3_eth.account.privateKeyToAccount(
                    self._private_key)
                self._account_address = self._account.address.lower()
        return self._account

    @property
    def account_address(self) -> Optional[str]:
        """Get the account address as a hexstr."""
        if not self._account_address:
            account = self.account
            if account:
                self._account_address = account.address.lower()
        return self._account_address

    @account_address.setter
    def account_address(self, address: str):
        """Set the account address to something other than the main one.
        This may be useful if you used anything other than the first account
        controlled by your private key.

        Args:
            address (str): account address
        """
        self._account_address = address.lower()

    @property
    def account_address_checksumed(self) -> Optional[str]:
        """Get checksummed account address.

        Returns:
            str: checkedsummed address
        """
        if self.account_address:
            return to_checksum_address(self.account_address)
        return None

    def sign_hash(self, hash_hex: Union[HexBytes, str]):
        """Sign hash_hex with eth-sign.
        Note: If you need to sign for 0x, then use
        `ZxWeb3Client.sign_hash_zx_compat`

        Args:
            hash_hex (:class:`HexBytes` or hexstr): hash to sign
                (must be convertile to `HexBytes`)

        Returns:
            :class:`ECSignature` instance
        """
        if not self._private_key:
            raise Exception("Please set the private_key for signing hash_hex")
        msg_hash_hexbytes = defunct_hash_message(HexBytes(hash_hex))
        ec_signature = self.web3_eth.account.signHash(
            msg_hash_hexbytes,
            private_key=self._private_key,
        )
        return ec_signature

    def get_eth_balance(self) -> Decimal:
        """Get ether balance associated with client address.

        Returns:
            Decimal: balance in ETH (NOT Wei)
        """
        balance = self.web3_eth.getBalance(self.account_address_checksumed)
        return from_wei(balance)

    def _invoke_function_call(self, func, tx_params=None, view_only=True):
        """Build and send a transaction and return its receipt hash.

        Args:
            func (Callable): Web3 function object constructed with the right
                paramters
            tx_params (:class:`TxParams`): transaction options (default:
                None)
            view_only (bool): whether to transact or view only (default:
                None)

        Returns:
            (:class:`HexBytes`) transaction hash
        """
        if view_only:
            return func.call()
        if not tx_params:
            tx_params = TxParams()
        if not tx_params.from_:
            tx_params.from_ = self.account_address_checksumed
        tx_params = tx_params.as_dict()
        if self._private_key:
            transaction = func.buildTransaction(tx_params)
            signed_tx = self.web3_eth.account.signTransaction(
                transaction, private_key=self._private_key)
            res = self.web3_eth.sendRawTransaction(
                signed_tx.rawTransaction)
        else:  # hopefully middleware will sign it...
            res = func.transact(tx_params)
        return res

    def _validate_and_checksum_address(self, address: str):
        """Validate address format and return checksum version."""
        if not self.web3_instance.isAddress(address):
            raise TypeError("Invalid address provided: {}".format(address))
        return to_checksum_address(address)
