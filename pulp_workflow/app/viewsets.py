from rest_framework import mixins

from pulpcore.plugin.viewsets import NamedModelViewSet, RolesMixin

from pulp_workflow.app.models import Workflow
from pulp_workflow.app.serializers import WorkflowSerializer


class WorkflowViewSet(
    NamedModelViewSet,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
    RolesMixin,
):
    """
    A ViewSet for managing Workflows.

    Workflows are created with their full set of tasks and are immutable thereafter; to
    change a workflow, delete it and create a new one.
    """

    queryset = Workflow.objects.all().prefetch_related("tasks")
    endpoint_name = "workflows"
    serializer_class = WorkflowSerializer
    ordering = "-pulp_created"
    filterset_fields = {
        "name": ["exact", "contains"],
        "state": ["exact", "in"],
    }
    queryset_filtering_required_permission = "workflow.view_workflow"

    DEFAULT_ACCESS_POLICY = {
        "statements": [
            {
                "action": ["list", "retrieve", "my_permissions"],
                "principal": "authenticated",
                "effect": "allow",
                "condition": "has_model_or_domain_or_obj_perms:workflow.view_workflow",
            },
            {
                "action": [
                    "create",
                    "destroy",
                    "list_roles",
                    "add_role",
                    "remove_role",
                ],
                "principal": "authenticated",
                "effect": "allow",
                "condition": "has_model_or_domain_or_obj_perms:workflow.change_workflow",
            },
        ],
        "queryset_scoping": {"function": "scope_queryset"},
    }
    LOCKED_ROLES = {
        "workflow.workflow_admin": [
            "workflow.view_workflow",
            "workflow.change_workflow",
            "workflow.delete_workflow",
            "workflow.manage_roles_workflow",
        ],
        "workflow.workflow_viewer": ["workflow.view_workflow"],
    }
