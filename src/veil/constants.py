"""
All constants should go in this file

author: officialcryptomaster@gmail.com
"""
from decimal import Decimal
from zero_ex.contract_addresses import NetworkId

NULL_ADDRESS = "0x0000000000000000000000000000000000000000"

ZERO = Decimal(0)
ZERO_STR = "0"
MAX_INT = Decimal(2) ** 256
MAX_INT_STR = "{:.0f}".format(MAX_INT)

DEFAULT_PAGE = 0
DEFAULT_PER_PAGE = 20

NETWORK_INFO = {
    NetworkId.MAINNET: {
        "veil_api_url": "https://api.veil.co/api/v1/",
    },
    NetworkId.KOVAN: {
        "veil_api_url": "https://api.kovan.veil.co/api/v1/",
    },
}
