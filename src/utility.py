from __future__ import annotations
import ast
import ctypes
import functools
import time
from typing import TYPE_CHECKING

import urllib3

if TYPE_CHECKING:
    from src.compass_logon import CompassLogon

# Disable requests' warnings about insecure requests
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# https://stackoverflow.com/a/8831937
def hash_code(text: str) -> int:
    """Implements Java's hashCode in python"""
    return functools.reduce(lambda code, char: ctypes.c_int32(31 * code + ord(char)).value, list(text), 0)


def compass_restify(data: dict) -> list:
    # JSON data MUST be in the rather odd format of {"Key": key, "Value": value} for each (key, value) pair
    return [{"Key": f"{k}", "Value": f"{v}"} for k, v in data.items()]


def jk_hash(logon: CompassLogon):
    # hash_code(f"{time.time() * 1000:.0f}")
    member_no = logon.cn
    key_hash = f"{time.time() * 1000:.0f}{logon.jk}{logon.mrn}{member_no}"  # JK, MRN & CN are all required.
    data = compass_restify({"pKeyHash": key_hash, "pCN": member_no})
    logon.post(f"{CompassSettings.base_url}/System/Preflight", json=data, verify=False)
    return key_hash


def cast(value):
    try:
        value = int(value)
    except (ValueError, TypeError):
        try:
            value = ast.literal_eval(str(value)) if value else value
        except (ValueError, TypeError, SyntaxError):
            pass
    return value


class CompassSettings:
    base_url = "https://compass.scouts.org.uk"
    org_number = 10000001
    total_requests = 0
