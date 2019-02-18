"""
All constants should go in this file

author: officialcryptomaster@gmail.com
"""
from enum import Enum
from decimal import Decimal

NULL_ADDRESS = "0x0000000000000000000000000000000000000000"

ZERO = Decimal(0)
ZERO_STR = "0"
MAX_INT = Decimal(2) ** 256
MAX_INT_STR = "{:.0f}".format(MAX_INT)


class NetworkId(Enum):
    """Network names correlated to their network identification numbers"""
    MAINNET = 1
    ROPSTEN = 3
    RINKEBY = 4
    KOVAN = 42
    GANACHE = 50


NETWORK_INFO = {
    NetworkId.MAINNET.value: {
        "name": "main",
        "veil_api_url": "https://api.veil.market/api/v1/",
    },
    NetworkId.KOVAN.value: {
        "name": "kovan",
        "veil_api_url": "https://api.kovan.veil.market/api/v1/",
    },
}
