git-annex connector for https://openneuro.com
=============================================

Install
-------

```
pip install .
```

Usage
-----

1. Get, and/or log in to, your https://openneuro.org account.
2. Go to https://openneuro.org/keygen and generate an API key.
3. `export OPENNEURO_TOKEN="<your_token>"`

(note: it's a bad habit to be `export`ing credentials; all that means is that subprocesses can see them, but best to keep them contained as much as possible. You can accomplish the same thing more securely with `OPENNEURO_TOKEN="<your_token>" ./openneuro-cli` or `OPENNEURO_TOKEN="<your_token>" git annex initremote ...`, that makes it only available to that specific command.)

Development
-----------

To set up a development environment, first get an API key as above, then either:

```
export PATH=`pwd`:$PATH
```

or

```
pip install -e .
```

Once set up (i.e. `git-annex-remote-openneuro` is on your $PATH), you can run the tests with

```
./ci.sh
```
