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

There are two tools in this repository:

* `openneuro-cli`, which interacts with the site
* `git-annex-remote-openneuro`, which is a plugin for `git-annex` enabling storage to openneuro

Development
-----------

Install the code in development mode:
```
pip install -e .
```
(you might want to make a virtualenv too; but it's not necessary)

To set up a development environment, get an account on https://openneuro.staging.sqm.io/
(you will need to log in via a Google account for this, unfortunately, ORCiD isn't setup with `staging`).
and get an API key at https://openneuro.staging.sqm.io/keygen.

Point yourself at `staging`:

```
export OPENNEURO_SERVER="https://openneuro.staging.sqm.io"
export OPENNEURO_TOKEN="<your_token>"
```


Once set up (i.e. `git-annex-remote-openneuro` is on your $PATH), you can run the `git-annex` tests with

```
./ci.sh
```
