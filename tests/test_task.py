#!/usr/bin/env python
# coding=utf-8
"""Test scriptworker.task
"""
import datetime
import mock
import os
import pytest
from scriptworker.context import Context
import scriptworker.task as task
import scriptworker.log as log
import taskcluster.async
from . import successful_queue, unsuccessful_queue, read

assert (successful_queue, unsuccessful_queue)  # silence flake8


@pytest.fixture(scope='function')
def context(tmpdir_factory):
    temp_dir = tmpdir_factory.mktemp("context", numbered=True)
    context = Context()
    context.config = {
        'log_dir': os.path.join(str(temp_dir), "log"),
        'artifact_dir': os.path.join(str(temp_dir), "artifact"),
        'work_dir': os.path.join(str(temp_dir), "work"),
        'artifact_upload_timeout': 200,
        'artifact_expiration_hours': 1,
        'reclaim_interval': .1,
        'task_script': ('bash', '-c', '>&2 echo bar && echo foo && exit 2'),
    }
    return context

mimetypes = {
    "/foo/bar/test.log": "text/plain",
    "/tmp/blah.tgz": "application/x-tar",
    "~/Firefox.dmg": "application/x-apple-diskimage",
}


class TestTask(object):
    def test_temp_queue(self, context, mocker):
        context.temp_credentials = {'a': 'b'}
        context.session = {'c': 'd'}
        mocker.patch('taskcluster.async.Queue')
        task.get_temp_queue(context)
        assert taskcluster.async.Queue.called_once_with({
            'credentials': context.temp_credentials,
        }, session=context.session)

    def test_expiration_datetime(self, context):
        now = datetime.datetime.utcnow()

        def utcnow():
            return now

        # make sure time differences don't screw up the test
        # for some reason pytest-mock isn't working for me here
        with mock.patch.object(datetime, 'datetime') as p:
            p.utcnow = utcnow
            expiration = task.get_expiration_datetime(context)
            diff = expiration.timestamp() - now.timestamp()
            assert diff == 3600

    @pytest.mark.parametrize("mimetypes", [(k, v) for k, v in sorted(mimetypes.items())])
    def test_guess_content_type(self, mimetypes):
        path, mimetype = mimetypes
        assert task.guess_content_type(path) == mimetype

    @pytest.mark.asyncio
    async def test_run_task(self, context):
        status = await task.run_task(context)
        log_file, error_file = log.get_log_filenames(context)
        assert read(log_file) in ("ERROR bar\nfoo\nexit code: 2\n", "foo\nERROR bar\nexit code: 2\n")
        assert read(error_file) == "bar\n"
        assert status == 2