from gettext import gettext as _

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from rest_framework import serializers
from rest_framework.validators import UniqueValidator

from pulpcore.plugin.models import TaskSchedule
from pulpcore.plugin.serializers import IdentityField, ModelSerializer, RelatedField

from pulp_workflow.app.models import (
    Workflow,
    WorkflowTask,
    WorkflowTaskArg,
    WorkflowTaskKwarg,
)


class ContentTypeNaturalKeyField(serializers.CharField):
    """A ``ContentType`` field serialized as ``"app_label.model"``."""

    def to_internal_value(self, data):
        value = super().to_internal_value(data)
        if value.count(".") != 1:
            raise serializers.ValidationError(
                _("Must be 'app_label.model', got {v!r}.").format(v=value)
            )
        try:
            return ContentType.objects.get_by_natural_key(*value.split("."))
        except ContentType.DoesNotExist:
            raise serializers.ValidationError(_("Unknown content type {v!r}.").format(v=value))

    def to_representation(self, value):
        return f"{value.app_label}.{value.model}"


def _validate_dynamic_consistency(attrs):
    if attrs.get("dynamic", False):
        if attrs.get("content_type") is None:
            raise serializers.ValidationError(
                _("'content_type' is required when 'dynamic' is true.")
            )
    elif attrs.get("content_type") is not None:
        raise serializers.ValidationError(
            _("'content_type' is only allowed when 'dynamic' is true.")
        )
    return attrs


class WorkflowTaskArgSerializer(serializers.ModelSerializer):
    """A single positional arg of a ``WorkflowTask``."""

    arg_index = serializers.IntegerField(min_value=0)
    dynamic = serializers.BooleanField(required=False, default=False)
    value = serializers.JSONField(
        required=False,
        allow_null=True,
        write_only=True,
        help_text=_("Literal value passed to the task. Write-only; values may be sensitive."),
    )
    content_type = ContentTypeNaturalKeyField(
        required=False,
        allow_null=True,
        help_text=_(
            "When ``dynamic`` is true, the 'app_label.model' of the previous task's created "
            "resource to resolve to a primary key at dispatch time."
        ),
    )

    class Meta:
        model = WorkflowTaskArg
        fields = ("arg_index", "dynamic", "value", "content_type")

    def validate(self, attrs):
        return _validate_dynamic_consistency(super().validate(attrs))


class WorkflowTaskKwargSerializer(serializers.ModelSerializer):
    """A single keyword arg of a ``WorkflowTask``."""

    kwarg_key = serializers.CharField()
    dynamic = serializers.BooleanField(required=False, default=False)
    value = serializers.JSONField(
        required=False,
        allow_null=True,
        write_only=True,
        help_text=_("Literal value passed to the task. Write-only; values may be sensitive."),
    )
    content_type = ContentTypeNaturalKeyField(
        required=False,
        allow_null=True,
        help_text=_(
            "When ``dynamic`` is true, the 'app_label.model' of the previous task's created "
            "resource to resolve to a primary key at dispatch time."
        ),
    )

    class Meta:
        model = WorkflowTaskKwarg
        fields = ("kwarg_key", "dynamic", "value", "content_type")

    def validate(self, attrs):
        return _validate_dynamic_consistency(super().validate(attrs))


class WorkflowTaskSerializer(serializers.ModelSerializer):
    """Serializer for a single task within a Workflow.

    Tasks are nested resources of a Workflow and have no standalone endpoint, so
    this uses DRF's plain ``ModelSerializer`` rather than pulpcore's hyperlinked
    base.
    """

    index = serializers.IntegerField(
        help_text=_("Execution order of this task within the workflow."),
        min_value=0,
    )
    task_name = serializers.CharField(
        help_text=_("The name of the task to be dispatched."),
    )
    task_args = WorkflowTaskArgSerializer(
        many=True,
        required=False,
        help_text=_("Positional arguments passed to the task."),
    )
    task_kwargs = WorkflowTaskKwargSerializer(
        many=True,
        required=False,
        help_text=_("Keyword arguments passed to the task."),
    )
    reserved_resources = serializers.ListField(
        child=serializers.CharField(),
        help_text=_("Resources to reserve when dispatching this task."),
        required=False,
        allow_null=True,
    )
    dispatched_task = RelatedField(
        help_text=_("The task dispatched, if any."),
        read_only=True,
        view_name="tasks-detail",
    )

    class Meta:
        model = WorkflowTask
        fields = (
            "index",
            "task_name",
            "task_args",
            "task_kwargs",
            "reserved_resources",
            "dispatched_task",
        )

    def validate_task_args(self, value):
        indexes = [a["arg_index"] for a in value]
        if len(set(indexes)) != len(indexes):
            raise serializers.ValidationError(_("arg_index values must be unique."))
        if indexes and sorted(indexes) != list(range(len(indexes))):
            raise serializers.ValidationError(
                _("arg_index values must be contiguous starting from 0.")
            )
        return value

    def validate_task_kwargs(self, value):
        keys = [kw["kwarg_key"] for kw in value]
        if len(set(keys)) != len(keys):
            raise serializers.ValidationError(_("kwarg_key values must be unique."))
        return value


class WorkflowSerializer(ModelSerializer):
    """Serializer for Workflow with nested tasks."""

    pulp_href = IdentityField(view_name="workflows-detail")
    name = serializers.CharField(
        help_text=_("The name of the workflow."),
        allow_blank=False,
        validators=[UniqueValidator(queryset=Workflow.objects.all())],
    )
    state = serializers.CharField(
        help_text=_(
            "The current state of the workflow. The possible values include:"
            " 'waiting', 'skipped', 'running', 'completed', 'failed', 'canceled' and 'canceling'."
        ),
        read_only=True,
    )
    start_time = serializers.DateTimeField(
        help_text=_(
            "When the workflow should begin executing. Defaults to now (immediate). A pulpcore "
            "TaskSchedule is created at this time to dispatch the execute_workflow task."
        ),
        required=False,
    )
    started_at = serializers.DateTimeField(
        help_text=_("Timestamp of when this workflow started execution."),
        read_only=True,
    )
    finished_at = serializers.DateTimeField(
        help_text=_("Timestamp of when this workflow stopped execution."),
        read_only=True,
    )
    error = serializers.JSONField(
        help_text=_(
            "A JSON object describing a fatal error encountered during the execution of this "
            "workflow."
        ),
        read_only=True,
    )
    current_task = serializers.SerializerMethodField(
        help_text=_("The index of the task currently being executed, if any."),
    )
    tasks = WorkflowTaskSerializer(
        many=True,
        help_text=_("The ordered tasks that make up this workflow."),
    )

    class Meta:
        model = Workflow
        fields = ModelSerializer.Meta.fields + (
            "name",
            "state",
            "start_time",
            "started_at",
            "finished_at",
            "error",
            "current_task",
            "tasks",
        )

    def get_current_task(self, obj) -> int | None:
        return obj.current_task.index if obj.current_task_id else None

    def validate_tasks(self, value):
        if not value:
            raise serializers.ValidationError(_("A workflow must have at least one task."))
        indexes = [task["index"] for task in value]
        if len(set(indexes)) != len(indexes):
            raise serializers.ValidationError(_("Task indexes must be unique within a workflow."))
        # Dynamic args reference the previous task's created resources, so task 0 cannot use them.
        for task in value:
            if task["index"] == 0:
                rows = task.get("task_args", []) + task.get("task_kwargs", [])
                if any(row.get("dynamic") for row in rows):
                    raise serializers.ValidationError(
                        _("Task 0 cannot have dynamic args (no previous task).")
                    )
        return value

    @transaction.atomic
    def create(self, validated_data):
        tasks_data = validated_data.pop("tasks")
        workflow = Workflow.objects.create(**validated_data)
        for task_data in tasks_data:
            task_args = task_data.pop("task_args", [])
            task_kwargs = task_data.pop("task_kwargs", [])
            wf_task = WorkflowTask.objects.create(workflow=workflow, **task_data)
            WorkflowTaskArg.objects.bulk_create(
                WorkflowTaskArg(workflow_task=wf_task, **row) for row in task_args
            )
            WorkflowTaskKwarg.objects.bulk_create(
                WorkflowTaskKwarg(workflow_task=wf_task, **row) for row in task_kwargs
            )

        # Schedule a one-shot dispatch of execute_workflow at start_time.
        # dispatch_interval=None makes pulpcore's scheduler fire it once and stop.
        TaskSchedule.objects.create(
            name=f"pulp_workflow.workflow:{workflow.pk}",
            task_name="pulp_workflow.app.tasks.execute_workflow",
            task_kwargs={"workflow_pk": str(workflow.pk)},
            next_dispatch=workflow.start_time,
            dispatch_interval=None,
        )
        return workflow


class WorkflowCancelSerializer(serializers.Serializer):
    """Serializer used to validate the body of a workflow cancel (PATCH) request."""

    state = serializers.CharField(
        help_text=_("The desired state of the workflow. Only 'canceled' is accepted."),
        required=True,
    )

    def validate_state(self, value):
        if value != "canceled":
            raise serializers.ValidationError(
                _("The only acceptable value for 'state' is 'canceled'.")
            )
        return value

    class Meta:
        fields = ("state",)
