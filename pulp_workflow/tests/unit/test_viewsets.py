from pulp_workflow.app.viewsets import WorkflowViewSet


def test_access_policy_requires_view_for_read():
    """Read actions require view_workflow permission."""
    policy = WorkflowViewSet.DEFAULT_ACCESS_POLICY
    read_stmt = policy["statements"][0]
    assert set(read_stmt["action"]) == {"list", "retrieve", "my_permissions"}
    assert "view_workflow" in read_stmt["condition"]


def test_access_policy_requires_change_for_write():
    """Write actions require change_workflow permission."""
    policy = WorkflowViewSet.DEFAULT_ACCESS_POLICY
    write_stmt = policy["statements"][1]
    assert "create" in write_stmt["action"]
    assert "destroy" in write_stmt["action"]
    assert "change_workflow" in write_stmt["condition"]


def test_locked_roles():
    """Admin and viewer roles are defined."""
    roles = WorkflowViewSet.LOCKED_ROLES
    assert "workflow.workflow_admin" in roles
    assert "workflow.workflow_viewer" in roles
    assert "workflow.view_workflow" in roles["workflow.workflow_viewer"]
    assert "workflow.change_workflow" in roles["workflow.workflow_admin"]
