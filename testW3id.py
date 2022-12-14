#!/usr/bin/evn python3

from collections import namedtuple
import csv
import os
import requests
from sys import exit
from enum import IntEnum
import argparse
from subprocess import run
from shutil import rmtree
from os.path import isdir
from glob import glob

W3ID_REPOSITORY = "https://github.com/perma-id/w3id.org"
W3ID_DOMAIN = "https://w3id.org/"
WORKDIR = os.path.abspath(".")
W3ID_DIR = os.path.join(WORKDIR, "w3id.org")
TESTS_DIR = os.path.join(WORKDIR, "tests")

TMP_DOMAIN = "http://localhost/"
VERSION = "1.0.0"


def buildMenu():
    description = """
    Testing utility for w3id redirect with apaches rewrite module
    """

    parser = argparse.ArgumentParser(description=description)

    parser.add_argument(
        "repository",
        help="url or path to a git repository containing the w3id rules, can be either the official w3id.org repository or a fork",
        default=W3ID_REPOSITORY,
        nargs="?",
    )

    parser.add_argument(
        "-o",
        "--online",
        action="store_true",
        help="test redirects directly with w3id.org (default: offline local testing)",
    )

    parser.add_argument(
        "-u",
        "--update",
        help="pull most recent version of w3id.org repository",
        action="store_true",
    )

    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "-v", "--verbosity", help="print verbose results", action="store_true"
    )
    group.add_argument(
        "-q",
        "--quiet",
        help="returns 0 if all tests run withough errors the number of failed test otherwise",
        action="store_true",
    )

    parser.add_argument("--version", action="version", version="%(prog)s " + VERSION)

    return parser


args = buildMenu().parse_args()


def getCurrentRepositoryUrl():
    if not isdir(W3ID_DIR):
        return ""

    os.chdir(W3ID_DIR)
    currentRepositoryUrl = run(
        "git remote get-url origin".split(), capture_output=True
    ).stdout
    currentRepositoryUrl = currentRepositoryUrl.decode("ascii").strip()
    os.chdir(WORKDIR)
    return currentRepositoryUrl


if getCurrentRepositoryUrl() != args.repository:
    rmtree(W3ID_DIR, ignore_errors=True)
    run(f"git clone -q --depth 1 {args.repository} {W3ID_DIR}".split())
else:
    if args.update:
        os.chdir(W3ID_DIR)
        run("git pull".split())
        os.chdir(WORKDIR)

if os.environ.get("DOCKER"):
    run(["httpd", "-k", "start"])

tests_csv = glob(os.path.join(TESTS_DIR, "*.csv"))[0]


class status(IntEnum):
    OK = 0
    WARN = 1
    ERROR = 2


class Results:
    status = status.OK
    matches = {}
    mismatches = {}
    responseList = []

    def __init__(self):
        self.status = status.OK
        self.matches = {}
        self.mismatches = {}
        self.responseList = []

    def setWarn(self):
        if self.status < status.WARN:
            self.status = status.WARN

    def setError(self):
        if self.status < status.ERROR:
            self.status = status.ERROR


Diff = namedtuple("Diff", "expected received")


def extractRequestAndRespnseHeaders(testcase):
    """Extract and seperate the items from a dict

    The extracted items contain keys that are prepended
    with `request_header_` or `response_header_`

    Keyword arguments:
    testcase -- a dict containing keys that are either prepended with `request_header_` or `response_header_`

    return -- a touple with two dicts the first contains
    """
    request_headers = {}
    response_header = {}
    for key in testcase.keys():
        if "request_header_" in key:
            request_headers[key[len("request_header_") :]] = testcase[key]
        elif "response_header_" in key:
            response_header[key[len("response_header_") :]] = testcase[key]

    return request_headers, response_header


def replaceW3idWithLocalhost(url):
    if url and not args.online:
        url = url.replace("https://w3id.org/", TMP_DOMAIN)
    return url


def replaceLocalhostWithW3id(url):
    if url and not args.online:
        url = url.replace(TMP_DOMAIN, "https://w3id.org/")
    return url


def processTestcase(testcase):
    request_headers, response_headers = extractRequestAndRespnseHeaders(testcase)
    responses = requests.get(
        replaceW3idWithLocalhost(testcase["request_url"]),
        headers=request_headers,
        allow_redirects=True,
    )
    responseList = responses.history + [responses]
    redirectIndex = int(testcase["redirection_test_index"]) if testcase["redirection_test_index"] else 0
    resp = responseList[redirectIndex]

    results = Results()
    results.responseList = [ (response.status_code, response.headers.get("location")) for response in responseList ]
    # as only redirects (code 3xx) send back a location header, use the location from the last redirect
    # or the request location if no redirect was given
    responseLocation = resp.headers.get("location") \
            if str(resp.status_code).startswith("3") \
            else \
                ( responseList[redirectIndex-1].headers.get("location") \
                    if redirectIndex>0 and redirectIndex-1 >= -len(responseList) \
                    else testcase["response_url"] \
                )
    resp.headers["location"] = replaceLocalhostWithW3id(responseLocation)
    if testcase["response_statuscode"]:

        if str(resp.status_code) != testcase["response_statuscode"]:
            results.setError()
            results.mismatches["statuscode"] = Diff(
                testcase["response_statuscode"], resp.status_code
            )
        else:
            results.matches["statuscode"] = Diff(
                testcase["response_statuscode"], resp.status_code
            )

    response_headers["Location"] = testcase["response_url"]
    for key, value in response_headers.items():
        if value:
            if not resp.headers.get(key) or value != resp.headers.get(key):
                if value in response_headers[key]:
                    results.setWarn()
                else:
                    results.setError()
                results.mismatches[key] = Diff(value, resp.headers.get(key))
            else:
                results.matches[key] = Diff(value, resp.headers.get(key))

    return results


testCaseId = 1

with open(tests_csv, newline="") as csvfile:
    testsReader = csv.DictReader(csvfile, delimiter=",", skipinitialspace=True)

    for testcase in testsReader:

        # Skip Comments
        if testcase["request_url"].startswith("#"):
            continue

        simple_output = "Testing: %d %s__[%s] --[%s]-> %s__[%s]" % (
            testCaseId,
            testcase["request_url"],
            testcase["request_header_accept"],
            testcase["response_statuscode"],
            testcase["response_url"],
            testcase["response_header_content-type"],
        )

        res = processTestcase(testcase)

        # Column Size for output
        cs1 = cs2 = cs3 = 20

        for item in [res.matches, res.mismatches]:
            cs1 = max(max([len(str(key)) for key in item.keys()], default=0), cs1 + 2)
            cs2 = max(
                max([len(str(value.expected)) for value in item.values()], default=0),
                cs2 + 2,
            )
            cs3 = max(
                max([len(str(value.received)) for value in item.values()], default=0),
                cs3 + 2,
            )

        if res.status != status.OK:
            print(f"Testcase {testCaseId} Get {testcase['request_url']} failed")
            print(f"Details: showing mismatches")
            for item in [res.matches, res.mismatches][1:]:
                for key, value in item.items():
                    print(f"\t{key:^{cs1}}")
                    print(f"\t{'expected':^{10}}{value.expected}")
                    print(f"\t{'received':^{10}}{value.received}")
                    print()
            print(res.responseList)
        else:
            print(f"Testcase {testCaseId} Get {testcase['request_url']} ok")

        testCaseId += 1
