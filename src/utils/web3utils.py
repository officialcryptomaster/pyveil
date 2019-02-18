"""
Web3 Utilities

author: officialcryptomaster@gmail.com
"""
from decimal import Decimal
from eth_account.messages import defunct_hash_message


def to_base_unit_amount(amount, decimals=18):
    """convert an amount to base unit amount string

    Keyword arguments:
    amount -- numeric or string which can be converted to numeric
    decimals -- integer number of decimal places in the base unit
    """
    return "{:.0f}".format(Decimal(amount) * 10 ** int(decimals))


def sign_order(
    order_hash,
    web3_instance,
    private_key
):
    """Sign order_hash via eth.signHash and convert ec_signature to a
    0x-compatible signature

    Keyword arguments:
    order_hash -- string hex of order hash
    web3_instance -- Web3 instance to sign the order with
    private_key -- string private key to use for signing the order
    """

    def to_32byte_hex(val):
        """Convert value to bytes32 hex"""
        return web3_instance.toHex(web3_instance.toBytes(val).rjust(32, b'\0'))

    def convert_ec_sig(ec_signature):
        """Make ec_signature compatible with 0x"""
        r = to_32byte_hex(ec_signature["r"])[2:]  # pylint: disable=invalid-name
        s = to_32byte_hex(ec_signature["s"])[2:]  # pylint: disable=invalid-name
        v = hex(ec_signature["v"])  # pylint: disable=invalid-name
        # Append 03 to specify signature type of eth-sign
        return v + r + s + "03"

    msg_hash = defunct_hash_message(hexstr=order_hash)
    ec_signature = web3_instance.eth.account.signHash(
        msg_hash, private_key=private_key)
    return convert_ec_sig(ec_signature=ec_signature)
