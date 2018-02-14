import logging
import unittest

from httprunner import exception, runner, testcase, utils


class ApiTestCase(unittest.TestCase):
    """ create a testcase.
    """
    def __init__(self, test_runner, testcase_dict):
        super(ApiTestCase, self).__init__()
        self.test_runner = test_runner
        self.testcase_dict = testcase_dict

    def runTest(self):
        """ run testcase and check result.
        """
        self.assertTrue(self.test_runner._run_test(self.testcase_dict))

class ApiTestSuite(unittest.TestSuite):
    """ create test suite with a testset, it may include one or several testcases.
        each suite should initialize a separate Runner() with testset config.
    @param
        (dict) testset
            {
                "name": "testset description",
                "config": {
                    "name": "testset description",
                    "requires": [],
                    "function_binds": {},
                    "variables": [],
                    "request": {}
                },
                "testcases": [
                    {
                        "name": "testcase description",
                        "variables": [],    # optional, override
                        "request": {},
                        "extract": {},      # optional
                        "validate": {}      # optional
                    },
                    testcase12
                ]
            }
        (dict) variables_mapping:
            passed in variables mapping, it will override variables in config block

    @return (instance) test result of testset
        Result(success, output)
    """
    def __init__(self, testset, variables_mapping=None, http_client_session=None):
        super(ApiTestSuite, self).__init__()

        self.config_dict = testset.get("config", {})
        variables = self.config_dict.get("variables", [])
        variables_mapping = variables_mapping or {}
        self.config_dict["variables"] = utils.override_variables_binds(variables, variables_mapping)

        self.test_runner = runner.Runner(self.config_dict, http_client_session)
        testcases = testset.get("testcases", [])
        self._add_tests_to_suite(testcases)

    def _add_tests_to_suite(self, testcases):
        for testcase_dict in testcases:
            if utils.PYTHON_VERSION == 3:
                ApiTestCase.runTest.__doc__ = testcase_dict['name']
            else:
                ApiTestCase.runTest.__func__.__doc__ = testcase_dict['name']

            test = ApiTestCase(self.test_runner, testcase_dict)
            [self.addTest(test) for _ in range(int(testcase_dict.get("times", 1)))]

    @property
    def output(self):
        output_variables_list = self.config_dict.get("output", [])
        return self.test_runner.extract_output(output_variables_list)

class TaskSuite(unittest.TestSuite):
    """ create test task suite with specified testcase path.
        each task suite may include one or several test suite.
    """
    def __init__(self, path, mapping=None, http_client_session=None):
        """
        @params
            path: path could be in several type
                - absolute/relative file path
                - absolute/relative folder path
                - list/set container with file(s) and/or folder(s)
            (dict) mapping:
                passed in variables mapping, it will override variables in config block
        """
        super(TaskSuite, self).__init__()
        mapping = mapping or {}

        if not isinstance(path, list):
            # absolute/relative file/folder path
            path = [path]

        # remove duplicate path
        path = set(path)

        testsets = testcase.load_testcases_by_path(path)
        if not testsets:
            raise exception.TestcaseNotFound

        self.suite_list = []
        for testset in testsets:
            suite = ApiTestSuite(testset, mapping, http_client_session)
            self.addTest(suite)
            self.suite_list.append(suite)

    @property
    def tasks(self):
        return self.suite_list


class Result(object):

    def __init__(self, success, output):
        self.success = success
        self.output = output

class LocustTask(object):

    def __init__(self, path, locust_client, mapping=None):
        mapping = mapping or {}
        self.task_suite = TaskSuite(path, mapping, locust_client)

    def run(self):
        for suite in self.task_suite:
            for test in suite:
                try:
                    test.runTest()
                except exception.MyBaseError as ex:
                    try:
                        from locust.events import request_failure
                        request_failure.fire(
                            request_type=test.testcase_dict.get("request", {}).get("method"),
                            name=test.testcase_dict.get("request", {}).get("url"),
                            response_time=0,
                            exception=ex
                        )
                    except ImportError:
                        logging.exception(
                            "Exception occured in testcase: {}".format(test.testcase_dict.get("name")))