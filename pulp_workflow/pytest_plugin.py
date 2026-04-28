import uuid

import pytest

from pulpcore.tests.functional.utils import BindingsNamespace


@pytest.fixture(scope="session")
def workflow_bindings(_api_client_set, bindings_cfg):
    """
    A namespace providing preconfigured pulp_workflow api clients.

    e.g. `workflow_bindings.WorkflowsApi.list()`.
    """
    from pulpcore.client import pulp_workflow as workflow_bindings_module

    api_client = workflow_bindings_module.ApiClient(bindings_cfg)
    _api_client_set.add(api_client)
    yield BindingsNamespace(workflow_bindings_module, api_client)
    _api_client_set.remove(api_client)


@pytest.fixture
def workflow_factory(workflow_bindings, add_to_cleanup):
    """A factory to generate a Workflow with auto-cleanup."""

    def _create_workflow(**kwargs):
        kwargs.setdefault("name", str(uuid.uuid4()))
        kwargs.setdefault(
            "tasks",
            [
                {
                    "index": 0,
                    "task_name": "pulpcore.app.tasks.orphan_cleanup",
                },
            ],
        )
        workflow = workflow_bindings.WorkflowsApi.create(kwargs)
        add_to_cleanup(workflow_bindings.WorkflowsApi, workflow.pulp_href)
        return workflow

    return _create_workflow
