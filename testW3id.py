from collections import namedtuple
import csv
import requests
from sys import argv
from sys import exit
from glob import glob
from enum import Enum


class status(Enum):
    OK = 0
    WARN = 1
    ERROR = 2


class Results():
    status = status.OK
    matches = {}
    mismatches = {}

    def __init__(self):
        self.status = status.OK
        self.matches = {}
        self.mismatches = {}


Diff = namedtuple('Diff', 'expected received')


def processHeaders(testcase):
    request_headers = {}
    response_header = {}
    for key in testcase.keys():
        if "request_header_" in key:
            request_headers[key[len("request_header_"):]] = testcase[key]
        elif "response_header" in key:
            response_header[key[len("response_header_"):]] = testcase[key]

    return request_headers, response_header


def processTestcase(testcase):
    request_headers, response_headers = processHeaders(testcase)
    resp = requests.get(testcase["request_url"],
                        headers=request_headers, allow_redirects=False)

    results = Results()
    if testcase["response_statuscode"]:

        if str(resp.status_code) != testcase["response_statuscode"]:
            results.status = status.ERROR
            results.mismatches["statuscode"] = Diff(
                testcase["response_statuscode"], resp.status_code)
        else:
            results.matches["statuscode"] = Diff(
                testcase["response_statuscode"], resp.status_code)

    response_headers["Location"] = testcase["response_url"]
    for key, value in response_headers.items():
        if value:
            if not resp.headers[key] or value not in resp.headers[key]:
                results.mismatches[key] = Diff(value, resp.headers[key])
            else:
                results.matches[key] = Diff(value, resp.headers[key])

    return results


tests_csv = ""
if len(argv) > 1:
    tests_csv = argv[1]
else:
    print("No tests.csv provided, exiting")
    exit(1)

testCaseId = 1

with open(tests_csv, newline='') as csvfile:
    testsReader = csv.DictReader(csvfile, delimiter=',', skipinitialspace=True)

    for testcase in testsReader:

        # Skip Comments
        if testcase['request_url'].startswith('#'):
            continue

        output = "Testing: %d %s__[%s] --[%s]-> %s__[%s]" \
            % (testCaseId,
               testcase["request_url"],
               testcase["request_header_accept"],
               testcase["response_statuscode"],
               testcase["response_url"],
               testcase["response_header_content-type"])
        # print(output)

        # Column Size for output
        res = processTestcase(testcase)
        cs1 = 20
        cs2 = 20
        cs3 = 20

        for item in [res.matches, res.mismatches]:
            cs1 = max(max([len(str(key))
                      for key in item.keys()], default=0), cs1 + 2)
            cs2 = max(max([len(str(value.expected))
                      for value in item.values()], default=0), cs2 + 2)
            cs3 = max(max([len(str(value.received))
                      for value in item.values()], default=0), cs3 + 2)
        # print([[[len(key), len(str(value.expected)), len(str(value.received))] for key, value in item.items()] for item in [res.matches, res.mismatches]])

        if res.status != status.OK:
            print(
                f"Testcase {testCaseId} Get {testcase['request_url']} failed")
            print(f"Details: showing mismatches")
            # print(f"{'':{cs1}}{'expected':^{cs2}}{'received':^{cs3}}")
            for item in [res.matches, res.mismatches][1:]:
                for key, value in item.items():
                    print(f"{key:^{cs1}}")
                    print(
                        f"{'expected':^{10}}{value.expected}")
                    print(
                        f"{'received':^{10}}{value.received}")
                    print()
                    # print(
                    #     f"{key:^{cs1}}{value.expected:^{cs2}}{value.received:^{cs3}}")
            print()
        else:
            print(f"Testcase {testCaseId} Get {testcase['request_url']} ok")

        testCaseId += 1
