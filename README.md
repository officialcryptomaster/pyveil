PyVeil Client
=============
[Pyveil Client](https://github.com/officialcryptomaster/pyveil) is a python client for interacting with [veil.co](https://veil.co) - a user-friendly prediction market based on [augur](https://www.augur.net/) and [0x](https://0x.org/).

Quick Start Guide
-----------------
### Initial Setup
Make sure you have `python3` and `virtualenv` installed. On Mac OS you can use [brew](https://brew.sh/) to install `python3` and then `pip3` (which is `python3`'s built-in package manager) to install virtualenv:
```
brew install python3
pip3 install virtualenv
```
Once you have confirmed `python3` and `virtualenv` are successfully installed, install all the dependencies using:
```
source setup
```
The above script will do two things:
1. It will create the `pyveil_env` virtual environment and install the python packages required for running PyVeil Client.
2. It will activate the virtualenv required for running PyVeil Client.

### Setting Up environment Variables
You will need two keys for using the Pyveil Client.
#### 1. Infura API Key
Make an account with [infura](infura.io) and get an API key so can interact with the Ethereum blockchain.
#### 2. Ethereum Wallet Private Key 
Get the private key from the Ethereum wallet that is associated with your veil account). **WARNING:** Be very careful as this is your account's spend key, so you need to make sure you are on a computer you trust.


Add the following environment variables to your OS's startup configuration (typical `.bashrc` or `.zshrc`):
```
INFURA_API_KEY=<your_infura_key_here>
PRIVATE_KEY=<your_wallet_key_here>
```

Using Jupyter Notebooks to Interactively Make a Bot
---------------------------------------------------
Make sure the environment is active (`source setup.py`). Then, run `jupyter` from the `./notebooks` directory using the command:
```
PYTHONPATH=../src jupyter notebook
```
The above command should open a notebook server in your default browser. Open the included `Veil Playground.ipynb` notebook to example usage of the API.

Tips
----
If you found this project useful, and would like to tip me ([officialcryptomaster](https://github.com/officialcryptomaster/)) you can send ETH or other ethereum assets to the following ETH address:
`0xe1FeFB3a5Ab56D5A961520CaBD75c3FaeDa6cB2b`
Thanks!